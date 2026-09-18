"""
Drop the orphaned Department.leave_block_list custom field and column.

This field pointed at a "Leave Block List" doctype that does not exist in this
bench (no hrms app installed) — a legacy artifact from before Leave Management
was split out of Frappe core. 0 of 26 real Department records used it. Its mere
presence in the schema (a Link field, regardless of reqd) breaks Frappe's own
test-record dependency-graph walk (frappe/tests/utils/generators.py) for any
test that reaches Department in its Link-field chain — this patch removes the
field and column outright. Safe to run even if already removed (idempotent).
"""

import frappe


def execute():
    cf_name = "Department-leave_block_list"
    if frappe.db.exists("Custom Field", cf_name):
        frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
        print(f"  Deleted Custom Field: {cf_name}")
    else:
        print(f"  Custom Field {cf_name} does not exist — skipping")

    existing_columns = {
        row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabDepartment`")
    }
    if "leave_block_list" in existing_columns:
        frappe.db.sql_ddl("ALTER TABLE `tabDepartment` DROP COLUMN `leave_block_list`")
        print("  Dropped column tabDepartment.leave_block_list")
    else:
        print("  tabDepartment.leave_block_list does not exist — skipping")
