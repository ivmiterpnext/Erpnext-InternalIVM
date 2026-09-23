"""
Drop the orphaned Designation.skills custom field.

Points at a "Designation Skill" doctype that doesn't exist in this bench (no
hrms app installed) — same root cause as the Department/Employee/Timesheet
fields removed by the two prior patches in this series. Unlike those, this is
a Table (child table) fieldtype, which creates no physical column on the
parent table, so there is no column to drop — only the Custom Field record
itself. Safe to run even if already removed (idempotent).
"""

import frappe


def execute():
	cf_name = "Designation-skills"
	if frappe.db.exists("Custom Field", cf_name):
		frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
		print(f"  Deleted Custom Field: {cf_name}")
	else:
		print(f"  Custom Field {cf_name} does not exist — skipping")
