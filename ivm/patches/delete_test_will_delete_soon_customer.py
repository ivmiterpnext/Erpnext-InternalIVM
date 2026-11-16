"""
Delete the leftover test Customer record "Test. Will Delete Soon." and its connected records.

This was a test/junk record (its only linked Issues are literally titled "Test Email 2 - Please
Disregard" and "test") that was never cleaned up. Deletes, in dependency order:

1. The 2 linked Issues (ISS-2023-115658, ISS-2023-97343) — plain Issue records, docstatus=0,
   no submit workflow to cancel first.
2. The single "iCorp Client Link Customer Candidate" child row referencing this Customer as a
   merge/assignment candidate (on parent iCorp Client Link 1314) — removed via the parent
   document's save, not a direct child-table delete, so the parent's own validation runs.
3. The Customer record itself. On prod, Opportunity CRM-OPP-2023-01838 still links to this
   Customer, so the delete raises frappe.LinkExistsError. That case is not fatal: the delete runs
   inside a savepoint, the savepoint is rolled back on LinkExistsError, and the Customer is
   disabled (disabled = 1) instead. The patch never raises for that case.

Safe to run repeatedly (idempotent) — each step checks existence first.
"""

import frappe

ISSUE_NAMES = ["ISS-2023-115658", "ISS-2023-97343"]
CUSTOMER_NAME = "Test. Will Delete Soon."
CUSTOMER_SAVEPOINT = "delete_test_will_delete_soon_customer"
ICORP_CLIENT_LINK_PARENT = "1314"


def execute():
	for name in ISSUE_NAMES:
		if not frappe.db.exists("Issue", name):
			print(f"  Issue {name} does not exist — skipping")
		elif frappe.db.get_value("Issue", name, "customer") != CUSTOMER_NAME:
			print(f"  Issue {name} is not linked to {CUSTOMER_NAME} — skipping")
		else:
			frappe.delete_doc("Issue", name, ignore_permissions=True, force=True)
			print(f"  Deleted Issue: {name}")

	if frappe.db.exists("iCorp Client Link", ICORP_CLIENT_LINK_PARENT):
		parent = frappe.get_doc("iCorp Client Link", ICORP_CLIENT_LINK_PARENT)
		original_count = len(parent.related_customers)
		parent.related_customers = [row for row in parent.related_customers if row.customer != CUSTOMER_NAME]
		if len(parent.related_customers) != original_count:
			parent.save(ignore_permissions=True)
			print(
				f"  Removed related_customers candidate row for {CUSTOMER_NAME} on iCorp Client Link {ICORP_CLIENT_LINK_PARENT}"
			)
		else:
			print(
				f"  No related_customers candidate row for {CUSTOMER_NAME} found on iCorp Client Link {ICORP_CLIENT_LINK_PARENT} — skipping"
			)
	else:
		print(f"  iCorp Client Link {ICORP_CLIENT_LINK_PARENT} does not exist — skipping")

	if frappe.db.exists("Customer", CUSTOMER_NAME):
		frappe.db.savepoint(CUSTOMER_SAVEPOINT)
		try:
			frappe.delete_doc("Customer", CUSTOMER_NAME, ignore_permissions=True)
			print(f"  Deleted Customer: {CUSTOMER_NAME}")
		except frappe.LinkExistsError as e:
			frappe.db.rollback(save_point=CUSTOMER_SAVEPOINT)
			if frappe.db.get_value("Customer", CUSTOMER_NAME, "disabled"):
				print(f"  Customer {CUSTOMER_NAME} still has links ({e}) — already disabled, not deleted")
			else:
				frappe.db.set_value("Customer", CUSTOMER_NAME, "disabled", 1)
				print(f"  Customer {CUSTOMER_NAME} still has links ({e}) — disabled instead of deleted")
	else:
		print(f"  Customer {CUSTOMER_NAME} does not exist — skipping")

	frappe.db.commit()
