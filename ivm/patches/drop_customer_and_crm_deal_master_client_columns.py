"""
Drop orphaned columns for fields removed as part of the master-client hierarchy rework:
- Customer.parent_account (dead field, fully superseded by custom_master_customer)
- CRM Deal.custom_master_client_id (superseded by the Master-association-label based
  custom_master_organization field)

Frappe does not drop columns automatically on migrate, so this patch removes the
leftover columns from the database. Safe to run even if columns/Custom Field
records do not exist (idempotent).
"""

import frappe


def execute():
	custom_fields_to_delete = {
		"Customer": ["parent_account"],
		"CRM Deal": ["custom_master_client_id"],
	}

	for doctype, fieldnames in custom_fields_to_delete.items():
		for fieldname in fieldnames:
			cf_name = f"{doctype}-{fieldname}"
			if frappe.db.exists("Custom Field", cf_name):
				frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
				print(f"  Deleted Custom Field: {cf_name}")
			else:
				print(f"  Custom Field {cf_name} does not exist — skipping")

	columns_to_drop = {
		"tabCustomer": ["parent_account"],
		"tabCRM Deal": ["custom_master_client_id"],
	}

	for table, columns in columns_to_drop.items():
		existing_columns = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}
		for column in columns:
			if column not in existing_columns:
				print(f"  {table}.{column} does not exist — skipping")
				continue
			frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
			print(f"  Dropped column {table}.{column}")
