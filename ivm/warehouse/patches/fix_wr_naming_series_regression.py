import frappe


def execute():
	doctype = "Warehouse Request"

	if not frappe.db.exists("DocType", doctype):
		return

	# Defensive normalization — guards against stale/mismatched naming_series
	# default/options on any environment not manually fixed
	frappe.db.sql(
		"""
		UPDATE `tabDocField`
		SET `default`=%s, options=%s
		WHERE parent=%s AND fieldname='naming_series'
		""",
		("WR - ", "WR - ", doctype),
	)

	# Repair any hash-named leftover records from the 2026-09-29 bug window
	bad = frappe.db.sql(
		"""
		SELECT name FROM `tabWarehouse Request`
		WHERE name NOT LIKE 'WR - %' AND name NOT LIKE 'WR-%'
		ORDER BY creation ASC
		""",
		as_dict=True,
	)

	max_num = (
		frappe.db.sql(
			"""
			SELECT MAX(CAST(REPLACE(REPLACE(name,'WR - ',''),'WR-','') AS UNSIGNED))
			FROM `tabWarehouse Request` WHERE name LIKE 'WR%'
			"""
		)[0][0]
		or 0
	)

	next_num = max_num
	for row in bad:
		next_num += 1
		new_name = f"WR - {next_num:05d}"
		frappe.rename_doc(doctype, row.name, new_name, force=True)

	frappe.db.sql("UPDATE `tabSeries` SET current=%s WHERE name='WR-'", (next_num,))
	frappe.db.commit()
