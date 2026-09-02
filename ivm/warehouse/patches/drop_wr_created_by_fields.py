import frappe


def execute():
	for col in ("created_by", "created_date"):
		if frappe.db.has_column("Warehouse Request", col):
			frappe.db.sql_ddl(f"ALTER TABLE `tabWarehouse Request` DROP COLUMN `{col}`")
