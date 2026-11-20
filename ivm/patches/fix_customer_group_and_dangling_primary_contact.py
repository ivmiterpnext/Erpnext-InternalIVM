"""
Fix two long-standing data-quality issues affecting nearly every Customer record, discovered
when trying to bulk-disable Customers through the UI and hitting a hard validation error on
essentially any Customer save:

1. `customer_group = "All Customer Groups"` (the Customer Group tree's root/group node, not a
   real leaf group) — a legacy artifact of the original 2023 Salesforce import, which never set
   an explicit group. ERPNext core's `Customer.validate_customer_group()` hard-`frappe.throw()`s
   on save whenever `customer_group` points at a group-type node, so ~98.6% of this org's
   Customers currently cannot be saved/edited/disabled through the UI at all.

   `create_missing_customers()` in the since-removed consolidation apply module already defaults new
   customer creations to "Commercial" for exactly this reason (see docs/agent/restore-from-prod.md
   Gotcha 4) — this patch applies the same default retroactively to existing customers.

2. `customer_primary_contact` pointing at a Contact record that no longer exists. Likely stale
   from historic Contact deletions/dedup over time, unrelated to the customer_group issue but
   hit the same discovery path. Cleared rather than guessed at — the Customer's other Contacts
   (linked via Dynamic Link, not this field) are untouched.

Uses direct SQL rather than frappe.get_doc()/save() deliberately: looping through ~5,000+
documents calling .save() would re-trigger the exact validate_customer_group() error this patch
exists to fix, and these are plain data corrections, not business-logic-driven changes.

Safe to run repeatedly (idempotent) — each run only touches rows still matching the bad state.
"""

import frappe


def execute():
	group_count = frappe.db.sql(
		"SELECT COUNT(*) FROM `tabCustomer` WHERE customer_group = 'All Customer Groups'"
	)[0][0]

	if group_count:
		if frappe.db.exists("Customer Group", "Commercial"):
			frappe.db.sql(
				"""
				UPDATE `tabCustomer`
				SET customer_group = 'Commercial'
				WHERE customer_group = 'All Customer Groups'
				"""
			)
			print(f"  Fixed customer_group on {group_count} Customer(s)")
		else:
			print(
				f"  WARNING: Customer Group 'Commercial' does not exist — skipping customer_group fix for {group_count} Customer(s)."
			)
	else:
		print("  No Customers with customer_group = 'All Customer Groups' — nothing to do.")

	dangling = frappe.db.sql(
		"""
		SELECT c.name
		FROM `tabCustomer` c
		WHERE c.customer_primary_contact IS NOT NULL
		  AND c.customer_primary_contact != ''
		  AND NOT EXISTS (
		      SELECT 1 FROM `tabContact` ct WHERE ct.name = c.customer_primary_contact
		  )
		""",
		as_dict=True,
	)

	if dangling:
		names = [row["name"] for row in dangling]
		frappe.db.sql(
			"""
			UPDATE `tabCustomer`
			SET customer_primary_contact = NULL
			WHERE name IN %(names)s
			""",
			{"names": names},
		)
		print(f"  Cleared dangling customer_primary_contact on {len(names)} Customer(s)")
	else:
		print("  No dangling customer_primary_contact values found — nothing to do.")

	frappe.db.commit()
	frappe.clear_cache(doctype="Customer")
