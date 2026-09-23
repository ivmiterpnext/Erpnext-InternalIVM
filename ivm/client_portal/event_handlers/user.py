"""
Enforce portal user role invariants on every User save.

Portal accounts (identified by holding the "Service Portal User" role) must
never simultaneously hold any role with desk_access=1 — if they do,
User.validate() -> set_system_user() -> has_desk_access() silently flips
user_type to "System User", granting Desk access to a client-facing account.

Multiple installed apps auto-assign desk_access=1 roles to User docs via
doc_events hooks that ivm does not control (e.g. erpnext.portal.utils
.set_default_role adds "Customer" on every save when a Contact links to a
Customer record). This hook runs on before_validate — before User.validate()
evaluates has_desk_access() — so the offending roles are removed before the
user_type recompute occurs.
"""

import frappe

PORTAL_ROLE = "Service Portal User"


def enforce_portal_user_roles(doc, method):
	portal_user_roles = {r.role for r in doc.get("roles", [])}
	if PORTAL_ROLE not in portal_user_roles:
		return

	desk_access_roles = set(frappe.get_all("Role", filters={"desk_access": 1}, pluck="name"))

	stripped = []
	for role_row in list(doc.roles):
		if role_row.role in desk_access_roles:
			doc.roles.remove(role_row)
			stripped.append(role_row.role)

	if stripped:
		frappe.logger().warning(f"Stripped desk-access roles {stripped} from portal user {doc.name}")
