import frappe


def create_custom_fields():
	"""Create custom fields required by the HubSpot integration.

	Adds a ``hubspot_deal_id`` field to the CRM Deal doctype so that
	deals created via the webhook can be cross-referenced back to
	HubSpot.  This function is idempotent and safe to call multiple
	times (e.g. during ``bench migrate``).
	"""
	custom_fields = {
		"CRM Deal": [
			{
				"fieldname": "hubspot_deal_id",
				"fieldtype": "Data",
				"label": "HubSpot Deal ID",
				"insert_after": "naming_series",
				"unique": 1,
				"read_only": 1,
				"no_copy": 1,
				"description": "Auto-populated by the HubSpot webhook integration.",
			},
		],
	}

	for doctype, fields in custom_fields.items():
		for field_def in fields:
			fieldname = field_def["fieldname"]
			if not frappe.db.exists(
				"Custom Field",
				{"dt": doctype, "fieldname": fieldname},
			):
				custom_field = frappe.new_doc("Custom Field")
				custom_field.update(
					{
						"dt": doctype,
						"module": "IVM_Integrations",
						**field_def,
					}
				)
				custom_field.insert(ignore_permissions=True)
				frappe.logger().info(
					f"Created custom field '{fieldname}' on '{doctype}'"
				)
