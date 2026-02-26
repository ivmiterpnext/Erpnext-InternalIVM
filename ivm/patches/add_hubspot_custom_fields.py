from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute() -> None:
	custom_fields = {
		"CRM Deal": [
			{
				"fieldname": "hubspot_deal_id",
				"fieldtype": "Data",
				"label": "HubSpot Deal ID",
				"unique": 1,
				"search_index": 1,
			},
			{
				"fieldname": "hubspot_last_modified",
				"fieldtype": "Datetime",
				"label": "HubSpot Last Modified",
			},
			{
				"fieldname": "hubspot_owner_id",
				"fieldtype": "Data",
				"label": "HubSpot Owner ID",
			},
			{
				"fieldname": "hubspot_pipeline_id",
				"fieldtype": "Data",
				"label": "HubSpot Pipeline ID",
			},
		],
		"Project": [
			{
				"fieldname": "crm_deal",
				"fieldtype": "Link",
				"label": "CRM Deal",
				"options": "CRM Deal",
				"unique": 1,
				"search_index": 1,
			},
		],
	}

	create_custom_fields(custom_fields, update=True)
