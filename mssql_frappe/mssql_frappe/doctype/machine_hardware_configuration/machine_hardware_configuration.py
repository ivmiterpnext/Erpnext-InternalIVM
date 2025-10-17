# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.api_utils import icorp_api_post, icorp_api_get, icorp_api_put, icorp_get_count
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict, to_iso8601
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_machine_id
from mssql_frappe.utils.filter_utils import filters_to_query_params


class MachineHardwareConfiguration(BaseVirtualDoctype):
	KEY_FIELD = "id"
	BOOL_FIELDS = ["is_in_effect"]
	SORT_FIELD_MAP = { "name": "code" }
	endpoint = "SV/MachineHardwareConfiguration"

	def db_insert(self, *args, **kwargs):
		try:
			data = self.get_valid_dict()
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)

			data["machine_name"] = get_machine_name_from_machine_id(self.machine_id)
			data["effective_date"] = to_iso8601(data["effective_date"])
			if data["end_date"]:
				data["end_date"] = to_iso8601(data["end_date"])
			data["hardware_connectivity_types"] = [
				row.connectivity_type_code for row in self.connectivity_types or []
			]

			endpoint = "SV/MachineHardwareConfiguration"
			response = icorp_api_post(endpoint, data)
			data = response.get("data")

			if not data or not data.get(self.KEY_FIELD):
				frappe.throw(f"Failed to create Machine Hardware Configuration in external API: {response}")

			self.name = str(data[self.KEY_FIELD])
			for k, v in data.items():
				setattr(self, k, v)

			clear_cache("machine_hardware_config_list", "machine_hardware_config_count")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineHardwareConfiguration.db_insert error")
			raise

	def post_process_loaded_data(self, data):
		if "hardware_connectivity_types" in data:
			self.set("connectivity_types", [
				{"connectivity_type_code": v} for v in data.get("hardware_connectivity_types", [])
			])

		set_attrs_from_dict(self, data)

	def db_update(self):
		try:
			data = self.get_valid_dict()
			data[self.KEY_FIELD] = data.pop("name")

			data = convert_fields_to_bool(data, self.BOOL_FIELDS)
			data["machine_name"] = get_machine_name_from_machine_id(self.machine_id)
			data["effective_date"] = to_iso8601(data["effective_date"])
			if data["end_date"]:
				data["end_date"] = to_iso8601(data["end_date"])
			data["hardware_connectivity_types"] = [
				row.connectivity_type_code for row in self.connectivity_types or []
			]

			endpoint = "SV/MachineHardwareConfiguration"
			response = icorp_api_put(endpoint, data)
			data = response.get("data")

			if not data or self.KEY_FIELD not in data:
				frappe.throw(f"Failed to create Machine Hardware Configuration in external API: {response}")

			self.name = str(data[self.KEY_FIELD])
			for k, v in data.items():
				setattr(self, k, v)

			clear_cache("machine_hardware_config_list", "machine_hardware_config_count")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineHardwareConfiguration.db_update error")
			raise

	@classmethod
	def get_count_from_api(cls, filters):
		return icorp_get_count(cls.endpoint, filters)
