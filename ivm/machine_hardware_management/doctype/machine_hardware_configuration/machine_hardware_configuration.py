# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.machine_hardware_management.doctype.base_virtual_doctype import BaseVirtualDoctype
from ivm.machine_hardware_management.utils.data_utils import set_attrs_from_dict, to_iso8601
from ivm.machine_hardware_management.doctype.machine_link.machine_link import get_machine_name_from_machine_id


class MachineHardwareConfiguration(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = ["is_in_effect"]
	FIELD_MAP = { "name": "id", "end_date": "effective_range_end_date" }
	endpoint = "SV/MachineHardwareConfiguration"

# Load from DB Overrides
	def process_load_response(self, data):
		if "machine_id" in data:
			self.machine_id = str(data["machine_id"])

		set_attrs_from_dict(self, data)

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

# Update Overrides
	def prepare_update_data(self, data):
		data["id"] = data.pop("name")
		data["machine_name"] = get_machine_name_from_machine_id(self.machine_id)
		data["effective_date"] = to_iso8601(data["effective_date"])

		if data["end_date"]:
			data["end_date"] = to_iso8601(data["end_date"])

		data["hardware_connectivity_types"] = [
			row.connectivity_type_code for row in self.connectivity_types or []
		]
		return data
