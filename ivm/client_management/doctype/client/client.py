# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from ivm.common.utils.base_virtual_doctype import BaseVirtualDoctype, api_data_to_frappe_dict, set_attrs_from_dict


class Client(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = [
		"is_active", "is_enhanced_client", "using_enhanced_assignments", "is_using_vend_return_machines"
]
	FIELD_MAP = { "name": "id" }
	endpoint = "Client"

# Get List Overrides
	@classmethod
	def process_list_response(cls, data, args):
		for row in data:
			if "name" in row:
				row["client_name"] = row["name"]
			if "partner_client_name" in row:
				row["partner_client_id"] = row["partner_client_name"]

		return api_data_to_frappe_dict(
			data,
			cls.FIELD_MAP["name"]
		)

# Load from DB Overrides
	def process_load_response(self, data):
		if data.get("id"):
			self.name = str(data["id"])
		if "name" in data:
			data["client_name"] = data["name"]

		set_attrs_from_dict(self, data)

# Insert Overrides
	def prepare_insert_data(self, data):
		data["name"] = data.get("client_name")

		if data["restriction_priority"] == "Most":
			data["restriction_priority_type_id"] = "1"
		elif data["restriction_priority"] == "Least":
			data["restriction_priority_type_id"] = "2"

		# if "time_zone_id" in data:
		# 	data["time_zone_id"] = str(data["time_zone_id"])

		return data

	def process_insert_response(self, data):
		if "name" in data:
			data["client_name"] = data.pop("name")

		# self._sync_agreement_fee_types()

		if not frappe.db.exists("Client Link", data.get("id")):
			frappe.get_doc({
				"doctype": "Client Link",
				"name": data.get("id"),
				"id": data.get("id"),
				"client_name": data.get("client_name"),
			}).insert(ignore_permissions=True)
