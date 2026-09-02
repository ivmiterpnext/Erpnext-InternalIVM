"""
Remove equipment_type field from Deployment Location and Warehouse Request doctypes.

The equipment_type field was removed from the Deployment Location and Warehouse Request
doctype JSON schemas directly (native fields, not Custom Fields) as part of moving
equipment_type tracking to the per-machine child doctypes instead. This patch defensively:

1. Deletes any stray DocField metadata rows for equipment_type on each doctype
2. Deletes any Custom Field override records (if they exist)
3. Clears the meta cache for each doctype
4. Drops the resulting orphaned DB columns (since schema sync never removes columns)

It is safe to run even if columns/records do not exist (idempotent).
"""

import frappe


def execute():
    # Doctypes and fieldname to clean up
    cleanup_pairs = [
        ("Deployment Location", "equipment_type"),
        ("Warehouse Request", "equipment_type"),
    ]

    # Step 1: Delete stray DocField rows and Custom Field records
    for doctype, fieldname in cleanup_pairs:
        # Delete DocField row(s) for this field from the doctype's field list
        frappe.db.delete("DocField", {"parent": doctype, "fieldname": fieldname})
        print(f"  Deleted DocField rows for {doctype}.{fieldname}")

        # Delete Custom Field override if it exists
        custom_field_name = f"{doctype}-{fieldname}"
        if frappe.db.exists("Custom Field", custom_field_name):
            frappe.delete_doc(
                "Custom Field",
                custom_field_name,
                ignore_permissions=True,
                force=True,
            )
            print(f"  Deleted Custom Field {custom_field_name}")
        else:
            print(f"  Custom Field {custom_field_name} does not exist — skipping")

    # Step 2: Clear meta cache for both doctypes
    for doctype, _ in cleanup_pairs:
        frappe.clear_cache(doctype=doctype)
        print(f"  Cleared meta cache for {doctype}")

    # Step 3: Drop the orphaned DB columns
    columns_to_drop = {
        "tabDeployment Location": [
            "equipment_type",
        ],
        "tabWarehouse Request": [
            "equipment_type",
        ],
    }

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
