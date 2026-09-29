import frappe


def execute():
	"""
	Clear module='IVM' on Custom Field and Property Setter records
	that don't belong to IVM. These were mis-tagged by
	populate_ivm_module_on_customizations.
	"""

	# Doctypes where IVM has NO legitimate Property Setters
	ps_clear_doctypes = [
		"Assignment Rule",
		"Campaign",
		"Dashboard Chart",
		"Email Account",
		"Employee",
		"Item Barcode",
		"Job Card",
		"LMS Certificate",
		"Material Request",
		"Pick List",
		"POS Invoice",
		"POS Invoice Item",
		"POS Profile",
		"Salary Slip",
		"User",
		"Delivery Note Item",
		"Packed Item",
	]

	# Doctypes where IVM has NO legitimate Custom Fields
	cf_clear_doctypes = [
		"Address",  # ERPNext owns is_your_company_address, tax_category
		"Communication",
		"Company",
		"Custom DocPerm",
		"Department",
		"Designation",
		"DocPerm",
		"DocShare",
		"Email Account",
		"Email Template",
		"Employee",
		"GoCardless Mandate",
		"Print Settings",
		"Web Form",
	]

	# Clear Property Setters
	if ps_clear_doctypes:
		placeholders = ", ".join(["%s"] * len(ps_clear_doctypes))
		frappe.db.sql(
			f"""UPDATE `tabProperty Setter`
                SET module = NULL
                WHERE module = 'IVM'
                AND doc_type IN ({placeholders})""",
			ps_clear_doctypes,
		)

	# Clear Custom Fields
	if cf_clear_doctypes:
		placeholders = ", ".join(["%s"] * len(cf_clear_doctypes))
		frappe.db.sql(
			f"""UPDATE `tabCustom Field`
                SET module = NULL
                WHERE module = 'IVM'
                AND dt IN ({placeholders})""",
			cf_clear_doctypes,
		)

	frappe.db.commit()
