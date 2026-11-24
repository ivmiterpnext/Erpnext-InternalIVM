"""Override for frappe.integrations.doctype.connected_app.connected_app.ConnectedApp.

Frappe core bug: ConnectedApp.get_active_token() takes a filelock before
refreshing an expired OAuth token, then calls `token_cache.reload()` to pick
up any concurrent update before deciding whether a refresh is still needed.
`reload()` issues a plain SELECT, which under MariaDB/InnoDB's default
REPEATABLE READ isolation can return a stale MVCC snapshot even after another
transaction has already committed a newer row for the same Token Cache
record — the filelock correctly serializes *who* gets to refresh, but does
not make the pre-refresh read itself see the latest committed data.
`check_if_latest()` (called moments later, inside `token_cache.save()`) does
its own fresh `for_update=True` fetch, which *does* see the latest row —
so the two reads disagree and `save()` raises `TimestampMismatchError`.

Reproduced directly: a plain SELECT inside an already-open transaction
returned stale data after a concurrent transaction committed a change to the
same row, while a `SELECT ... FOR UPDATE` on that same still-open
transaction immediately saw the fresh data.

Fix: replace `token_cache.reload()` with a `for_update=True` re-fetch, which
forces a locking read that always sees the latest committed data regardless
of this transaction's snapshot. Also add a retry-on-conflict as a cheap
backstop.

Remove this patch when Frappe core fixes the bug upstream.

NOTE: This class is registered via `override_doctype_class` in hooks.py and
is imported lazily by Frappe only when a "Connected App" document is
instantiated (a bound frappe.local context). Do NOT import this module eagerly
from ivm/__init__.py — doing so pulls in core's connected_app.py module-level
code, which touches frappe.conf before frappe.init() may have run, raising
"RuntimeError: object is not bound" in unbound contexts like bench's
app-command discovery probe. See ivm/overrides/connected_app_callback_lock.py
for the separate, eagerly-safe monkeypatch that handles the OAuth callback
endpoint.
"""

import frappe
from frappe.integrations.doctype.connected_app.connected_app import ConnectedApp
from frappe.integrations.frappe_providers.email_oauth import FRAPPE_CLOUD_RELAY, relay_refresh
from frappe.utils.synchronization import filelock
from oauthlib.oauth2 import InvalidGrantError


class CustomConnectedApp(ConnectedApp):
	def get_active_token(self, user=None):
		user = user or frappe.session.user
		token_cache = self.get_token_cache(user)
		if token_cache and token_cache.is_expired():
			try:
				with filelock(f"token_cache_{token_cache.name}"):
					# `for_update=True` forces a locking read that always sees the
					# latest committed data, unlike reload()'s plain SELECT which can
					# return a stale REPEATABLE READ snapshot. See module docstring.
					token_cache = frappe.get_doc("Token Cache", token_cache.name, for_update=True)
					if not token_cache.is_expired():
						return token_cache

					token = self._fetch_refreshed_token(user)
					self._save_token_with_retry(token_cache, token)
			except Exception as e:
				self.log_error("Token Refresh Error")
				# Central passes on the provider's error code as the message
				if isinstance(e, InvalidGrantError) or str(e) == "invalid_grant":
					# in a job, so neither the caller's rollback nor another worker's row lock gets in the way
					frappe.enqueue(  # not after commit: a rolled-back caller would drop the job  # nosemgrep
						"frappe.integrations.doctype.connected_app.connected_app.delete_token_cache",
						job_id=f"delete_token_cache:{token_cache.name}",
						deduplicate=True,
						name=token_cache.name,
						modified=token_cache.modified,
					)
				return None

		return token_cache

	def _fetch_refreshed_token(self, user):
		if (self.token_uri or "").startswith(FRAPPE_CLOUD_RELAY):
			return relay_refresh(self, self.get_token_cache(user))

		oauth_session = self.get_oauth2_session(user)
		return oauth_session.refresh_token(
			body=f"redirect_uri={self.redirect_uri}",
			token_url=self.token_uri,
		)

	def _save_token_with_retry(self, token_cache, token):
		try:
			token_cache.update_data(token)
		except frappe.TimestampMismatchError:
			token_cache = frappe.get_doc("Token Cache", token_cache.name, for_update=True)
			token_cache.update_data(token)
