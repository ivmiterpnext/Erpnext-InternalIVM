"""
Provision the automation service account used by internal warehouse
automation (e.g. auto-creating Delivery Notes from Warehouse Requests)
that needs full Stock module permissions regardless of which user
triggered the originating save.
"""

import frappe

AUTOMATION_USER = "automation@ivminc.com"


def execute() -> None:
	if frappe.db.exists("User", AUTOMATION_USER):
		return

	user = frappe.new_doc("User")
	user.email = AUTOMATION_USER
	user.first_name = "Automation"
	user.user_type = "System User"
	user.send_welcome_email = 0
	user.enabled = 1

	user.append("roles", {"role": "Stock Manager"})

	user.insert(ignore_permissions=True)
	print(f"  Created automation service user '{AUTOMATION_USER}'")
