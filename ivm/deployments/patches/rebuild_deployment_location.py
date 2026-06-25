"""
Export old Deployment Location data to CSV and drop the table.

The old Deployment Location doctype (tree-based, linked to Opportunity) is being
replaced with a new doctype of the same name (flat, linked to CRM Deal). Since the
schemas are completely different, this patch exports existing records to a CSV in
the site's private/files directory for archival, then drops the table so Frappe's
model sync can recreate it fresh from the new JSON definition.

The CSV files can be found in the site's private/files directory.
"""

import csv
import os
from datetime import datetime

import frappe

# Frappe system tables that store records keyed by doctype name.
# Each entry is (table_name, doctype_column, docname_column_or_None).
SYSTEM_TABLES = [
    ("tabComment", "reference_doctype", "reference_name"),
    ("tabVersion", "doctype", "docname"),
    ("tabDocShare", "share_doctype", "share_name"),
    ("tabActivity Log", "reference_doctype", "reference_name"),
    ("tabView Log", "reference_doctype", "reference_name"),
    ("tabCommunication Link", "link_doctype", "link_name"),
    ("tabFile", "attached_to_doctype", "attached_to_name"),
    ("tabTag Link", "document_type", "document_name"),
]


def execute():
    if not frappe.db.sql("SHOW TABLES LIKE 'tabDeployment Location'"):
        return

    count_result = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabDeployment Location`"
    )
    count = count_result[0][0] if count_result else 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = os.path.join(
        frappe.get_site_path("private", "files"),
        f"deployment_location_archive_{timestamp}",
    )
    os.makedirs(export_dir, exist_ok=True)

    if count:
        _export_table_to_csv(export_dir, "deployment_location")

    # Export any linked system records (comments, versions, files, etc.)
    _export_system_records(export_dir)

    # Delete the old DocType record and its children so model sync
    # treats this as a fresh install and recreates the table from JSON
    frappe.db.sql("DELETE FROM `tabDocField` WHERE parent='Deployment Location'")
    frappe.db.sql("DELETE FROM `tabDocPerm` WHERE parent='Deployment Location'")
    frappe.db.sql("DELETE FROM `tabDocType` WHERE name='Deployment Location'")

    # Clean up system records that would be orphaned
    for table, dt_col, _dn_col in SYSTEM_TABLES:
        try:
            frappe.db.sql(
                f"DELETE FROM `{table}` WHERE `{dt_col}` = 'Deployment Location'"
            )
        except Exception:
            pass

    # Commit pending DML before DDL
    frappe.db.commit()

    # Drop the old table — model sync will recreate from the new JSON
    frappe.db.sql_ddl("DROP TABLE `tabDeployment Location`")

def _export_table_to_csv(export_dir, slug):
    """Export the main Deployment Location table to CSV."""
    filepath = os.path.join(export_dir, f"{slug}.csv")

    columns_result = frappe.db.sql(
        "SHOW COLUMNS FROM `tabDeployment Location`"
    )
    column_names = [row[0] for row in columns_result]

    records = frappe.db.sql(
        "SELECT * FROM `tabDeployment Location`", as_dict=True
    )

    _write_csv(filepath, column_names, records)
    print(f"Exported {len(records)} Deployment Location records to: {filepath}")

def _export_system_records(export_dir):
    """Export any system records (comments, files, versions, etc.) linked to
    old Deployment Location documents."""
    
    for table, dt_col, _dn_col in SYSTEM_TABLES:
        try:
            records = frappe.db.sql(
                f"SELECT * FROM `{table}` WHERE `{dt_col}` = 'Deployment Location'",
                as_dict=True,
            )
        except Exception:
            continue

        if not records:
            continue

        slug = table.replace("tab", "").replace(" ", "_").lower()
        filepath = os.path.join(export_dir, f"{slug}.csv")

        _write_csv(filepath, list(records[0].keys()), records)
        print(f"Exported {len(records)} {table} records to: {filepath}")

def _write_csv(filepath, fieldnames, records):
    with open(filepath, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record)
