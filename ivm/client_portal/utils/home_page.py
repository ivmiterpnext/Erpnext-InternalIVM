"""
Home page resolution for portal users.

Gated on user_type rather than role name — Administrator's roles include
every role in the system (frappe.permissions.get_roles special-cases it),
so a naive role_home_page dict matching "Service Portal User" would
incorrectly redirect Administrator to the portal dashboard. user_type ==
"Website User" is frappe's own convention for this distinction (see
frappe.utils.user.is_portal_user) and correctly excludes Administrator
and all other System Users.
"""

import frappe


def get_website_user_home_page(user):
	if frappe.db.get_value("User", user, "user_type") != "Website User":
		return None
	if "Service Portal User" in frappe.get_roles(user):
		return "dashboard"
	return None
