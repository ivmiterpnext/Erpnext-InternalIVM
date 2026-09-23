"""
Provision portal users for Service Quote signers.
"""

import frappe


# Deliberately not @frappe.whitelist()'d — this only ever runs server-side via
# frappe.call() from Service Quote.on_submit (event_handlers/service_quote.py).
# Whitelisting it would let any authenticated user force-provision a portal
# account (and trigger a password-reset email) for an arbitrary Contact by
# calling /api/method/ivm.client_portal.services.provisioning.ensure_portal_user
# directly with any contact name — there is no permission check on the
# `contact` argument, by design, since it's meant to be trusted-internal-only.
def ensure_portal_user(contact):
	"""
	Ensure a Contact has a linked User for portal access.

	If the Contact already has a user, return early (no-op).
	Otherwise:
	- Extract email from the Contact's primary email row.
	- Create a new Website User with role "Service Portal User".
	- Link the user to the Contact.
	- Send a password reset/portal invite email.
	"""
	contact_doc = frappe.get_doc("Contact", contact)

	# If user already set, no-op
	if contact_doc.user:
		return {"status": "ok", "message": "User already linked"}

	# Get primary email from contact.email_ids
	email = None
	if contact_doc.email_ids:
		for email_row in contact_doc.email_ids:
			if email_row.is_primary:
				email = email_row.email_id
				break
		# Fallback to first email if no primary
		if not email and contact_doc.email_ids:
			email = contact_doc.email_ids[0].email_id

	if not email:
		return {"status": "error", "message": "No email found on Contact"}

	# Ensure "Service Portal User" role exists
	if not frappe.db.exists("Role", "Service Portal User"):
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": "Service Portal User",
				"desk_access": 0,
			}
		).insert(ignore_permissions=True)

	# Create new User
	user_doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": contact_doc.first_name or "Portal",
			"last_name": contact_doc.last_name or "User",
			"user_type": "Website User",
			"send_welcome_email": 0,
		}
	)
	user_doc.insert(ignore_permissions=True)

	# Add role
	user_doc.add_roles("Service Portal User")

	# Strip any roles auto-assigned by other installed apps (e.g. LMS/Wiki
	# apps assigning default roles to every new User) — this account should
	# only ever have the one narrowly-scoped portal role. Some of those roles
	# can carry desk_access=1, which silently promotes user_type to "System
	# User" via User.set_system_user() — explicitly correct both.
	user_doc.reload()
	for role_row in list(user_doc.roles):
		if role_row.role != "Service Portal User":
			user_doc.remove_roles(role_row.role)

	frappe.db.set_value("User", user_doc.name, "user_type", "Website User")

	# Link user to contact (use set_value to avoid timestamp mismatch)
	frappe.db.set_value("Contact", contact, "user", user_doc.name)

	# Send password reset email (portal invite)
	from frappe.core.doctype.user.user import reset_password

	reset_password(user_doc.name)

	return {"status": "ok", "message": f"User {user_doc.name} created and invited"}
