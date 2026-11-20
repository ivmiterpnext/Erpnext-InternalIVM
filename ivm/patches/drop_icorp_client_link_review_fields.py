"""
Remove the review-only schema from iCorp Client Link (customer consolidation teardown).

The DocFields were removed from icorp_client_link.json, and the child doctype
"iCorp Client Link Customer Candidate" (related_customers' target) was deleted
from the repo. Frappe does not drop columns or DocType records automatically, so
this patch removes what is left on existing sites:
- the child DocType record and its table (related_customers is a Table field, so
  no column exists for it)
- the columns for the review-only Data/Select/Link/Check/Small Text fields
  (section_break_proposal and related_customers never had columns)

Safe to re-run; every step checks existence first.
"""

import frappe

CHILD_DOCTYPE = "iCorp Client Link Customer Candidate"
PARENT_TABLE = "tabiCorp Client Link"
REVIEW_COLUMNS = [
	"review_status",
	"match_status",
	"proposed_customer",
	"parent_customer",
	"has_multiple_customer_candidates",
	"duplicate_name_siblings",
	"match_evidence",
]


def execute():
	if frappe.db.exists("DocType", CHILD_DOCTYPE):
		frappe.delete_doc("DocType", CHILD_DOCTYPE, ignore_permissions=True, force=True)

	# Commit pending deletes before DDL (ImplicitCommitError otherwise — see CLAUDE.md).
	frappe.db.commit()

	frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{CHILD_DOCTYPE}`")

	existing_columns = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{PARENT_TABLE}`")}
	for column in REVIEW_COLUMNS:
		if column in existing_columns:
			frappe.db.sql_ddl(f"ALTER TABLE `{PARENT_TABLE}` DROP COLUMN `{column}`")
