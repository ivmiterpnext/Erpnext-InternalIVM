"""
Reduce the 5 O365 connected-user service accounts (emailsync*@ivminc.com)
from System Manager down to Inbox User, and remove 2 long-dormant,
zero-footprint contractor accounts (Suneet Sharma, korecent.com domain,
created 2023-09-17, never active since, zero owned records).

Root cause / context: these 5 service accounts exist solely to hold the
OAuth Connected App / Token Cache identity for the 5 O365-linked Email
Accounts (Accounts Receivable, ICS/IT/IVM Support, Vending Management).
Tracing the OAuth authorize/callback flow in
frappe.integrations.doctype.connected_app.connected_app confirms every
Token Cache write uses ignore_permissions=True, and Token Cache/Connected
App both already grant "All" users read (Token Cache also grants
delete-if_owner) -- so the connected_user's own role has zero bearing on
whether the OAuth flow or the background pull_emails job functions. The
only thing actually required is read access to Email Account (to see the
"Authorize API Access" button), which the stock "Inbox User" role already
covers. System Manager grants full site-wide admin and was unnecessary
over-provisioning -- it's also why these 5 service accounts were
incorrectly included in Email Account's auto-disable notification broadcast
(frappe.utils.user.get_system_managers()), discovered during the 2026-11
"Invalid Mail Server" investigation.

The 2 Suneet Sharma accounts were reviewed individually: created and active
for a single day (2023-09-17), never logged in since, zero owned records
across Communication/ToDo/Issue/Email Account. Deletion is not forced --
if Frappe's own link-integrity check (LinkExistsError) finds anything we
didn't catch, that account is skipped and reported rather than destroying
linked data.

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

USERS_TO_DELETE = [
	"suneetsharma1666@gmail.com",
	"suneet@korecent.com",
]


def execute():
	# 1. Swap System Manager -> Inbox User on the 5 O365 service accounts
	for user in SERVICE_ACCOUNTS:
		if not frappe.db.exists("User", user):
			print(f"  User {user} does not exist -- skipping role swap")
			continue

		user_doc = frappe.get_doc("User", user)
		roles = {d.role for d in user_doc.roles}
		changed = False

		if "System Manager" in roles:
			user_doc.roles = [d for d in user_doc.roles if d.role != "System Manager"]
			changed = True
			print(f"  Removed System Manager from {user}")

		if "Inbox User" not in roles:
			user_doc.append("roles", {"role": "Inbox User"})
			changed = True
			print(f"  Added Inbox User to {user}")

		if changed:
			user_doc.save(ignore_permissions=True)
		else:
			print(f"  {user} already correctly roled -- skipping")

	frappe.clear_cache(user="*")

	# 2. Delete the 2 dormant contractor accounts (not forced -- let Frappe's
	# own link-integrity check block this if there's anything we missed)
	for user in USERS_TO_DELETE:
		if not frappe.db.exists("User", user):
			print(f"  User {user} does not exist -- skipping")
			continue

		try:
			frappe.delete_doc("User", user, ignore_permissions=True)
			print(f"  Deleted User: {user}")
		except frappe.LinkExistsError as e:
			print(f"  Could not delete {user}, linked records exist: {e}")
