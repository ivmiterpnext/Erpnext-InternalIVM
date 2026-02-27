# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.ivm.utils.base_virtual_doctype import BaseVirtualDoctype
from ivm.ivm.utils.case_utils import convert_fields_to_bool
from ivm.ivm.utils.data_utils import set_attrs_from_dict
from ivm.machine_hardware_management.doctype.machine_link.machine_link import get_machine_name_from_machine_id


class MachineAddress(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = ["is_active"]
	FIELD_MAP = {"name": "id"}
	endpoint = "SV/Machine/Address"

# Get List Overrides
	@classmethod
	def preprocess_filters(cls, filters, args=None):
		new_filters = []
		for f in filters or []:
			if f[1] == "machine_id":
				new_filters.append([f[0], "Id", f[2], f[3]])
			else:
				new_filters.append(f)

		if args and not any(f[1] == "Id" for f in new_filters):
			if args.get("parent") and args.get("parenttype") == "Machine":
				new_filters.append(["=", "Id", args.get("parent")])
		return new_filters

	@classmethod
	def process_list_response(cls, data, args):
		items = []
		addresses = data.get("address_machines", [])
		machine_name = data.get("name")
		for address in addresses:
			address_row = dict(address)
			address_row["name"] = str(address_row.pop("id", ""))
			address_row["machine_name"] = machine_name or ""

			# Build a readable address string for the address_id field
			address_row["address_id"] = ", ".join(
				filter(None, [
					address_row.get("address_line_one"),
					address_row.get("address_line_two"),
					address_row.get("city"),
					address_row.get("state_code"),
					address_row.get("postal_code"),
				])
			)
			items.append(address_row)
		return items

# Load From DB Overrides
	def process_load_response(self, data):
		if data.get("id"):
			self.name = str(data["id"])
		if "machine_id" in data:
			data["machine_name"] = get_machine_name_from_machine_id(data["machine_id"])
		set_attrs_from_dict(self, data)

# Insert Overrides
	def prepare_insert_data(self, data):
		data = convert_fields_to_bool(data, self.BOOL_FIELDS)
		if "machine_id" in data:
			data["machine_name"] = get_machine_name_from_machine_id(data["machine_id"])
		return data

	def process_insert_response(self, data):
		if "id" in data:
			self.name = str(data["id"])
		print("Insert response data:", data)
		set_attrs_from_dict(self, data)

# Update Overrides
	def prepare_update_data(self, data):
		data = convert_fields_to_bool(data, self.BOOL_FIELDS)
		if "machine_id" in data:
			data["machine_name"] = get_machine_name_from_machine_id(data["machine_id"])
		return data

	def process_update_response(self, data):
		if "id" in data:
			data["address_id"] = str(data["id"])
		set_attrs_from_dict(self, data)

# Count Overrides
	@classmethod
	def extract_count(cls, response):
		data = response.get("data", {}).get("address_machines", [])
		return len(data)
