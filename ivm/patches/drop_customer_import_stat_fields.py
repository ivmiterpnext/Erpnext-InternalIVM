"""One-time removal of 14 Customer fields that were typed in during the 2023 Salesforce import
and are no longer read by anything except the Customer form itself (checked: no Server Script,
Client Script, report, print format, number card, dashboard chart, or fetch_from reads any of
them). Backs up every non-empty value to a CSV in private files before dropping anything, copies
total_client_employees into employees where employees is blank (employees is kept current by
provisioning and stays), then deletes the Custom Field records, the unused Accounts Audit report,
and the database columns. Safe to run repeatedly — each step checks first and is a no-op once
done. Registered in patches.txt."""

import csv
import os

import frappe

DROP_FIELDS = [
	"mthly_total_sv_value",
	"custom_total_account_sv",
	"number_of_locations_not_equipped",
	"number_of_locations_with_equipment",
	"total_client_locations",
	"custom_total_pieces_of_equipment_in_place",
	"custom_total_number_of_pieces",
	"custom_average_value_per_piece",
	"number_of_lockers_in_place",
	"number_of_machines_in_place",
	"machines",
	"custom_per_machine_value",
	"total_life_time_value",
	"total_client_employees",
]


def execute():
	existing_columns = {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabCustomer`")}
	present = [f for f in DROP_FIELDS if f in existing_columns]

	if present:
		_backup_nonempty_values(present)

		if "total_client_employees" in present and "employees" in existing_columns:
			frappe.db.sql(
				"""
				UPDATE `tabCustomer`
				SET employees = total_client_employees
				WHERE (employees IS NULL OR employees = 0)
				  AND total_client_employees IS NOT NULL AND total_client_employees > 0
				"""
			)

	for fieldname in DROP_FIELDS:
		custom_field_name = f"Customer-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, force=True, ignore_permissions=True)

	if frappe.db.exists("Report", "Accounts Audit"):
		frappe.delete_doc("Report", "Accounts Audit", force=True, ignore_permissions=True)

	existing_columns_after_deletes = {row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabCustomer`")}
	for fieldname in DROP_FIELDS:
		if fieldname in existing_columns_after_deletes:
			frappe.db.sql_ddl(f"ALTER TABLE `tabCustomer` DROP COLUMN `{fieldname}`")

	frappe.clear_cache(doctype="Customer")


def _backup_nonempty_values(present: list[str]) -> None:
	select_cols = ", ".join(f"`{f}`" for f in present)
	where_clause = " OR ".join(f"(`{f}` IS NOT NULL AND `{f}` != '' AND `{f}` != '0')" for f in present)
	rows = frappe.db.sql(
		f"SELECT `name`, {select_cols} FROM `tabCustomer` WHERE {where_clause}",
		as_dict=True,
	)
	if not rows:
		return

	backup_path = frappe.get_site_path(
		"private", "files", f"customer_dropped_fields_backup_{frappe.utils.nowdate()}.csv"
	)
	with open(backup_path, "w", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=["name", *present])
		writer.writeheader()
		for row in rows:
			writer.writerow(row)

	print(f"Backed up {len(rows)} Customer row(s) to {backup_path}")
