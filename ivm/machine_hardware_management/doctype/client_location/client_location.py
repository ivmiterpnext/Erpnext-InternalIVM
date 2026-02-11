# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.machine_hardware_management.doctype.base_virtual_doctype import BaseVirtualDoctype, api_data_to_frappe_dict, set_attrs_from_dict


class ClientLocation(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = [
		"is_active", "is_restricted", "is_allow_anyone_vend", "is_pin_required"
	]
	FIELD_MAP = { "name": "id" }
	endpoint = "SV/Location"

# Get List Overrides
	@classmethod
	def process_list_response(cls, data, args):
		for row in data:
			if "name" in row:
				row["location_name"] = row["name"]
			if "client_name" in row:
				row["client_id"] = row["client_name"]

		return api_data_to_frappe_dict(
			data,
			cls.FIELD_MAP["name"]
		)

	# Load from DB Overrides
	def process_load_response(self, data):
		if data.get("id"):
			self.name = str(data["id"])
		if "name" in data:
			data["location_name"] = data["name"]

		codes = data.get("restriction_type_code_list")
		code_list = [c.strip() for c in codes.split(",") if c.strip()] if codes else []
		data["restriction_type_code_list"] = code_list

		child_table_map = {
			"restriction_type_code_list": "restriction_type_code",
		}

		set_attrs_from_dict(self, data, child_table_map)
