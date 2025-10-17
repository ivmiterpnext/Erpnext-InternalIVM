# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.case_utils import convert_fields_to_bool
from mssql_frappe.utils.api_utils import icorp_api_get, icorp_api_post
from mssql_frappe.utils.data_utils import build_sort_params
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_machine_id


class MachineAddress(BaseVirtualDoctype):
	KEY_FIELD = "address_id"
	BOOL_FIELDS = ["is_active"]
	SORT_FIELD_MAP = { "name": "id" }

	endpoint = "SV/Machine/Address"

	# Insert
	def pre_insert_data(self, data):
		data = convert_fields_to_bool(data, self.BOOL_FIELDS)
		data["machine_name"] = get_machine_name_from_machine_id(self.id)
		return data

	# Get List
	@classmethod
	def extract_list_data(cls, response):
		# Custom extraction for address_machines
		return response.get("data", {}).get("address_machines", [])

	@classmethod
	def process_list_data(cls, data, args):
		items = []
		machine_name = args.get("machine_name") or args.get("_api_response", {}).get("data", {}).get("name")

		for address in data:
			address_row = dict(address)
			address_row["address_id"] = str(address_row.pop("id", ""))
			address_row["machine_name"] = machine_name or ""
			address_row["name"] = frappe.generate_hash(length=10)
			items.append(address_row)

		return items

	# Get Count
	@classmethod
	def get_count_from_api(cls, filters):
		# Translate machine_id to name for the API
		if filters and "machine_id" in filters:
			machine_name = get_machine_name_from_machine_id(filters["machine_id"])
			if machine_name:
				filters["name"] = machine_name
			filters.pop("machine_id")
		filter_query = filters_to_query_params(filters)
		endpoint = "SV/Machine/Address?"
		if filter_query:
			endpoint += f"&{filter_query}"
		try:
			response = icorp_api_get(endpoint)
			data = response.get("data", {}).get("address_machines", [])
			return len(data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineAddress.get_count_from_api error")
			return 0
