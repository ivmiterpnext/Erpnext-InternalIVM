"""
Trim the 5 O365 connected-user service accounts (emailsync*@ivminc.com)
down to the single "Inbox User" role, removing all other roles.

Follow-up to ivm.patches.scope_down_email_service_accounts_and_remove_dormant_users,
which only removed "System Manager". A full audit found these accounts
still held 59 roles each -- effectively every role in the system (Script
Manager, Website Manager, HR Manager, Accounts Manager, Stock Manager,
CEO/COO/CTO, Workspace Manager, Sales Master Manager, etc.).

Full code-path tracing confirmed "Inbox User" (plain read on Email Account)
is the only role these accounts actually need:
- frappe.integrations.doctype.connected_app.connected_app.initiate_web_application_flow
  only calls self.check_permission("write") when authorizing on behalf of a
  DIFFERENT user than the one logged in; the actual self-service flow used
  here (log in as the service account, click "Authorize API Access")
  never hits that branch.
- frappe.email.doctype.email_account.email_account.pull_emails only checks
  read on Email Account, evaluated against the scheduler/worker's own
  session, not the connected_user field's roles.
- get_oauth_token/get_active_token are pure Token Cache lookups with no
  permission check.
- ivm/hooks.py has no custom has_permission/permission_query_conditions
  override for Email Account, Connected App, or Token Cache.

Safe to run repeatedly (idempotent).
"""

import frappe

SERVICE_ACCOUNTS = [
	"emailsync@ivminc.com",
	"emailsync1@ivminc.com",
	"emailsync2@ivminc.com",
	"emailsync3@ivminc.com",
	"emailsync4@ivminc.com",
]


def execute():
	for user in SERVICE_ACCOUNTS:
		if not frappe.db.exists("User", user):
			print(f"  User {user} does not exist -- skipping")
			continue

		user_doc = frappe.get_doc("User", user)
		current_roles = {d.role for d in user_doc.roles}

		if current_roles == {"Inbox User"}:
			print(f"  {user} already trimmed to Inbox User only -- skipping")
			continue

		removed = sorted(current_roles - {"Inbox User"})
		user_doc.roles = [d for d in user_doc.roles if d.role == "Inbox User"]

		if "Inbox User" not in {d.role for d in user_doc.roles}:
			user_doc.append("roles", {"role": "Inbox User"})

		user_doc.save(ignore_permissions=True)
		print(f"  Trimmed {user} to Inbox User only (removed {len(removed)} roles: {', '.join(removed)})")

	frappe.clear_cache(user="*")
