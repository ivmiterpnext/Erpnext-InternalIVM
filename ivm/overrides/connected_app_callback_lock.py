"""Override for frappe.integrations.doctype.connected_app.connected_app.callback.

Frappe core's OAuth re-authorization callback endpoint writes directly to a
Token Cache row (`token_cache.update_data(token)`) without taking the
per-token-cache filelock that `ConnectedApp.get_active_token()` uses (see
ivm/overrides/connected_app_token_refresh.py for that half of the fix). This
means a manual re-authorization through this endpoint can race a concurrent
background token refresh for the same Token Cache row.

This override wraps that same write in the same filelock, so every writer to
a given Token Cache row serializes through one lock. Registered via
`override_whitelisted_methods` in hooks.py rather than a module-level
monkeypatch: that hook resolves this function lazily, per-request, by dotted
string lookup, with zero eager import at process start — unlike a
monkeypatch applied from ivm/__init__.py, which would force-import core's
connected_app.py (and its fragile frappe.conf-touching top-level code) before
frappe.init() may have run, e.g. during bench's app-command discovery probe.

Remove this patch when Frappe core fixes the bug upstream.
"""

from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.utils.synchronization import filelock


@frappe.whitelist(methods=["GET"], allow_guest=True)
def callback(code: str | None = None, state: str | None = None):
	"""Same as connected_app.callback(), except the token write is now
	serialized through the same per-token-cache filelock that
	CustomConnectedApp.get_active_token() uses, so a manual re-authorization
	through this endpoint can never race a background token refresh for the
	same Token Cache row.
	"""
	if frappe.session.user == "Guest":
		frappe.local.response["type"] = "redirect"
		frappe.local.response["location"] = "/login?" + urlencode({"redirect-to": frappe.request.url})
		return

	path = frappe.request.path[1:].split("/")
	if len(path) != 4 or not path[3]:
		frappe.throw(_("Invalid Parameters."))

	connected_app = frappe.get_doc("Connected App", path[3])
	token_cache = frappe.get_doc("Token Cache", connected_app.name + "-" + frappe.session.user)

	if state != token_cache.state:
		frappe.throw(_("Invalid token state! Check if the token has been created by the OAuth user."))

	oauth_session = connected_app.get_oauth2_session(init=True)
	query_params = connected_app.get_query_params()
	token = oauth_session.fetch_token(
		connected_app.token_uri,
		code=code,
		client_secret=connected_app.get_password("client_secret"),
		include_client_id=True,
		**query_params,
	)
	with filelock(f"token_cache_{token_cache.name}"):
		token_cache.update_data(token)

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = token_cache.get("success_uri") or connected_app.get_url()
