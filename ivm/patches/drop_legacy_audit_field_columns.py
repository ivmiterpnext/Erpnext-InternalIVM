"""
Drop legacy audit field columns from multiple doctypes.

These custom fields (custom_created_date, custom_created_by, custom_modified_date,
custom_modified_by, custom_last_modified_date, created_by) were CRM migration shims
that duplicated native Frappe fields (creation, owner, modified, modified_by).
They have been removed from the schema but Frappe does not automatically drop columns,
so this patch removes the leftover columns from the database.

It is safe to run even if columns do not exist (idempotent).
"""

import frappe


def execute():
    # Map of doctype -> list of fieldnames to delete from Custom Field
    custom_fields_to_delete = {
        "Issue": [
            "created_date",
            "custom_created_date",
            "custom_created_by",
            "custom_modified_date",
            "custom_modified_by",
        ],
        "Lead": [
            "custom_created_date",
            "custom_last_modified_date",
            "created_by",
        ],
        "Customer": [
            "custom_created_date",
            "custom_last_modified_date",
        ],
        "Opportunity": [
            "custom_last_modified_date",
        ],
        "Task": [
            "custom_created_by",
            "custom_created_date",
        ],
    }

    # First, delete Custom Field records to prevent them from being re-synced
    for doctype, fieldnames in custom_fields_to_delete.items():
        for fieldname in fieldnames:
            cf_name = f"{doctype}-{fieldname}"
            if frappe.db.exists("Custom Field", cf_name):
                frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
                print(f"  Deleted Custom Field: {cf_name}")
            else:
                print(f"  Custom Field {cf_name} does not exist — skipping")

    # Map of table -> list of columns to drop
    columns_to_drop = {
        "tabIssue": [
            "created_date",
            "custom_created_date",
            "custom_created_by",
            "custom_modified_date",
            "custom_modified_by",
        ],
        "tabLead": [
            "custom_created_date",
            "custom_last_modified_date",
            "created_by",
        ],
        "tabCustomer": [
            "custom_created_date",
            "custom_last_modified_date",
        ],
        "tabOpportunity": [
            "custom_last_modified_date",
        ],
        "tabTask": [
            "custom_created_by",
            "custom_created_date",
        ],
    }

    # Then drop the columns
    for table, columns in columns_to_drop.items():
        # Get existing columns for this table
        existing_columns = {
            row[0]
            for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")
        }

        for column in columns:
            if column not in existing_columns:
                print(f"  {table}.{column} does not exist — skipping")
                continue

            frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
            print(f"  Dropped column {table}.{column}")
