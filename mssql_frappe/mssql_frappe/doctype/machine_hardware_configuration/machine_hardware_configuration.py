# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.data_utils import set_attrs_from_dict, to_iso8601
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_machine_id


class MachineHardwareConfiguration(BaseVirtualDoctype):
	KEY_FIELD = "id"
	BOOL_FIELDS = ["is_in_effect"]
	SORT_FIELD_MAP = { "name": "code" }
	endpoint = "SV/MachineHardwareConfiguration"

# Insert Overrides
	def prepare_insert_data(self, data):
		data["machine_name"] = get_machine_name_from_machine_id(self.machine_id)
		data["effective_date"] = to_iso8601(data["effective_date"])

		if data["end_date"]:
			data["end_date"] = to_iso8601(data["end_date"])

		data["hardware_connectivity_types"] = [
			row.connectivity_type_code for row in self.connectivity_types or []
		]
		return data

# Load from DB Overrides
	def process_load_response(self, data):
		if "machine_id" in data:
			self.machine_id = str(data["machine_id"])

		set_attrs_from_dict(self, data)

# Update Overrides
	def prepare_update_data(self, data):
		data["machine_name"] = get_machine_name_from_machine_id(self.machine_id)
		data["effective_date"] = to_iso8601(data["effective_date"])

		if data["end_date"]:
			data["end_date"] = to_iso8601(data["end_date"])

		data["hardware_connectivity_types"] = [
			row.connectivity_type_code for row in self.connectivity_types or []
		]
		return data
