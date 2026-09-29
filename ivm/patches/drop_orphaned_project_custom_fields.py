"""
Drop orphaned Project custom fields and their database columns.

These custom fields were created during early development but are no longer
used or referenced in the Project doctype. This patch removes both the
Custom Field records and their corresponding database columns.

Must run AFTER populate_ivm_module_on_customizations to ensure proper
module attribution before deletion.
"""

import frappe

ORPHAN_FIELDS = [
	"Project-asset",
	"Project-business_hours",
	"Project-custom_column_break_doqa7",
	"Project-custom_column_break_vmaqw",
	"Project-custom_hidden_fields",
	"Project-custom_master_client_id",
	"Project-is_refurbished",
	"Project-number_of_compact_lockers",
]

COLUMNS_TO_DROP = [
	"asset",
	"business_hours",
	"custom_master_client_id",
	"is_refurbished",
	"number_of_compact_lockers",
]


def execute():
	# First, delete Custom Field records to prevent them from being re-synced
	for name in ORPHAN_FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
			print(f"  Deleted Custom Field: {name}")
		else:
			print(f"  Custom Field {name} does not exist — skipping")

	# Must commit before DDL to avoid ImplicitCommitError (pending deletes = open transaction)
	frappe.db.commit()

	# Get existing columns for the Project table
	existing_columns = {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabProject`")}

	# Then drop the columns
	for col in COLUMNS_TO_DROP:
		if col not in existing_columns:
			print(f"  tabProject.{col} does not exist — skipping")
			continue

		frappe.db.sql_ddl(f"ALTER TABLE `tabProject` DROP COLUMN `{col}`")
		print(f"  Dropped column tabProject.{col}")
