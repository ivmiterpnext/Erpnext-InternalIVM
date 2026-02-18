# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.common.utils.base_virtual_doctype import BaseVirtualDoctype
from ivm.machine_hardware_management.doctype.machine_link.machine_link import get_machine_name_from_machine_id, get_machine_id_from_machine_name
from ivm.common.utils.case_utils import api_data_to_frappe_dict

class MachineActivityLog(BaseVirtualDoctype):
	API_TYPE = "icorp"
	FIELD_MAP = { "name": "id", "machine_id": "machine_name" }
	endpoint = "SV/MachineActivityLog"

# Get List Overrides
	@classmethod
	def preprocess_filters(cls, filters):
		new_filters = []

		for f in filters or []:
			if f[1] == "machine_id":
				machine_name = get_machine_name_from_machine_id(f[3])
				if machine_name:
					new_filters.append([f[0], "machine_name", f[2], machine_name])
				else:
					continue
			else:
				new_filters.append(f)
		return new_filters

	@classmethod
	def process_list_response(cls, data, args):
		for row in data:
			if "machine_name" in row:
				row["machine_id"] = get_machine_id_from_machine_name(row["machine_name"])
			if "id" in row:
				row["name"] = str(row["id"])

		return api_data_to_frappe_dict(
			data,
			cls.FIELD_MAP["name"]
		)

# Load from DB Overrides
	def load_from_db(self):
		raise NotImplementedError

# Insert Overrides
	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

# Update Overrides
	def db_update(self):
		raise NotImplementedError

# Delete Overrides
	def delete(self):
		raise NotImplementedError
