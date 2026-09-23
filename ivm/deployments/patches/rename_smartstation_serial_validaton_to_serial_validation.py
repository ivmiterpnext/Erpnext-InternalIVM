import frappe


def execute():
	"""Rename 'serial_validaton' (typo) to 'serial_validation' on Deployment SmartStation Details.

	Pre_model_sync so the column rename happens before Frappe syncs the new
	schema (which expects 'serial_validation').
	"""
	table = "tabDeployment SmartStation Details"
	columns = [c.column for c in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`", as_dict=True)]

	has_old = "serial_validaton" in columns
	has_new = "serial_validation" in columns

	if has_old and not has_new:
		frappe.db.sql(f"ALTER TABLE `{table}` CHANGE `serial_validaton` `serial_validation` varchar(140)")
	elif has_old and has_new:
		frappe.db.sql(
			f"UPDATE `{table}` SET `serial_validation` = `serial_validaton` "
			"WHERE (`serial_validation` IS NULL OR `serial_validation` = '') "
			"AND `serial_validaton` IS NOT NULL AND `serial_validaton` != ''"
		)
		frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `serial_validaton`")

	frappe.db.commit()
