"""
Drop the orphaned custom_client_id column from the CRM Deal table.

The field was renamed to custom_customer. Frappe does not drop columns
automatically on migrate, so this patch removes the leftover column.
It is safe to run even if the column does not exist.
"""

import frappe


def execute():
    table = "tabCRM Deal"
    column = "custom_client_id"

    existing_columns = {
        row[0]
        for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")
    }

    if column not in existing_columns:
        print(f"{table}.{column} does not exist — nothing to do.")
        return

    frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
    print(f"Dropped column {table}.{column}.")
