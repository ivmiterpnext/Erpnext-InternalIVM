"""
Drop 7 orphaned legacy HR custom fields and their columns.

These Custom Fields point at doctypes (Appraisal Template, Shift Type, Employment
Type, Employee Grade, Employee Health Insurance, Job Applicant, Salary Slip) that
do not exist in this bench (no hrms app installed) — legacy artifacts from before
Leave/HR management was split out of Frappe core, same category as the separately
patched Department.leave_block_list. Confirmed unused: 0 of 3 real Employee
records populate any of the 5 Employee fields; Designation and Timesheet have 0
real records at all. Their mere presence as Link fields (regardless of reqd)
breaks Frappe's own test-record dependency-graph walk (frappe/tests/utils/generators.py)
for any test that reaches Designation/Employee/Timesheet in its Link-field chain.
Safe to run even if already removed (idempotent).
"""

import frappe


def execute():
	custom_fields_to_delete = {
		"Designation": ["appraisal_template"],
		"Employee": [
			"grade",
			"default_shift",
			"job_applicant",
			"employment_type",
			"health_insurance_provider",
		],
		"Timesheet": ["salary_slip"],
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
		"tabDesignation": ["appraisal_template"],
		"tabEmployee": [
			"grade",
			"default_shift",
			"job_applicant",
			"employment_type",
			"health_insurance_provider",
		],
		"tabTimesheet": ["salary_slip"],
	}

	for table, columns in columns_to_drop.items():
		existing_columns = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}
		for column in columns:
			if column not in existing_columns:
				print(f"  {table}.{column} does not exist — skipping")
				continue
			frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
			print(f"  Dropped column {table}.{column}")
