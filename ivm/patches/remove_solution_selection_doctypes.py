"""
Remove the orphaned Opportunity-solution Table MultiSelect field and the two
DB-only custom DocTypes it depended on (Solution Selection, Solution).

Both DocTypes were created via the UI (custom=1) and never exported to code
or fixtures, so any freshly-created site (e.g. test.local) failed
sync_customizations with "DocType Solution Selection not found" as soon as
ivm/ivm/custom/opportunity.json referenced it. The field held 3 rows on a
single legacy 2025 Opportunity; Opportunity itself is superseded by CRM Deal.

Removing the block from opportunity.json only stops it being re-synced — it
does not delete the live records on existing sites (dev/prod), and
delete_doc("DocType", ...) does not drop the underlying table. This patch
does both explicitly. Safe to re-run; no-op on sites that never had them.
"""

import frappe

CUSTOM_FIELD = "Opportunity-solution"
# Child table first: it links to Solution.
DOCTYPES = ["Solution Selection", "Solution"]


def execute():
	if frappe.db.exists("Custom Field", CUSTOM_FIELD):
		frappe.delete_doc("Custom Field", CUSTOM_FIELD, ignore_permissions=True, force=True)

	for doctype in DOCTYPES:
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, ignore_permissions=True, force=True)

	# Commit pending deletes before DDL (ImplicitCommitError otherwise — see CLAUDE.md).
	frappe.db.commit()

	for doctype in DOCTYPES:
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")
