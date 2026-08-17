"""
Drop the legacy modified_by1/modified_date fields from Warehouse Request.

These native fields duplicated Frappe's built-in modified/modified_by and were
populated by a live before_save Client Script ("Warehouse Request Modified
Date"). No reader was found anywhere in server scripts, reports, or workspace
filters for either field — write-only dead weight. Removed from the DocType
JSON's fields/field_order; this patch drops the leftover DB columns and
deletes the writer Client Script (fixture sync never deletes records absent
from the JSON, so this must be explicit).

Safe to run repeatedly (idempotent).
"""

import frappe


def execute():
    scripts_to_delete = [
        "Warehouse Request Created Date",
        "Warehouse Request Modified By",
        "Warehouse Request Modified Date",
    ]
    for name in scripts_to_delete:
        if frappe.db.exists("Client Script", name):
            frappe.delete_doc("Client Script", name, ignore_permissions=True, force=True)
            print(f"  Deleted Client Script: {name}")
        else:
            print(f"  Client Script {name} does not exist — skipping")

    columns_to_drop = ["modified_by1", "modified_date"]
    existing_columns = {
        row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabWarehouse Request`")
    }
    for column in columns_to_drop:
        if column not in existing_columns:
            print(f"  tabWarehouse Request.{column} does not exist — skipping")
            continue
        frappe.db.commit()
        frappe.db.sql_ddl(f"ALTER TABLE `tabWarehouse Request` DROP COLUMN `{column}`")
        print(f"  Dropped column tabWarehouse Request.{column}")

    frappe.clear_cache(doctype="Warehouse Request")
