# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.api_utils import icorp_api_get, icorp_api_post
from mssql_frappe.utils.data_utils import build_sort_params
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache_by_prefix
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_machine_id



class MachineAddress(Document):
	_total_count = None

	KEY_FIELD = "address_id"
	BOOL_FIELDS = ["is_active"]
	SORT_FIELD_MAP = { "name": "id" }

	def check_if_latest(self):
		pass  # Disable optimistic locking for virtual DocType

	def validate_set_only_once(self):
		pass # Disable "Set Only Once" validation for virtual DocType

	@property
	def _action(self):
		# Always return "save" if not set
		return getattr(self, "__action", "save")

	def db_insert(self, *args, **kwargs):
		try:
			data = self.get_valid_dict()
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)
			data.machine_name = get_machine_name_from_machine_id(self.id)

			endpoint = "SV/Machine/Address"
			response = icorp_api_post(endpoint, data)

			data = response.get("data")

			if not data or not data.get(self.KEY_FIELD):
				frappe.throw(f"Failed to create Machine Address in external API: {response}")

			self.name = str(data[self.KEY_FIELD])
			for k, v in data.items():
				setattr(self, k, v)

			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineAddress.db_insert error")
			raise


	def load_from_db(self):
		if self.name and self.name.startswith("new-"):
			return
		raise NotImplementedError

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=30, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		filter_query = filters_to_query_params(filters)
		sort_query = build_sort_params(order_by, MachineAddress.SORT_FIELD_MAP) if order_by else []

		cache_key = f"machine_address_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
		cached = frappe.cache().get_value(cache_key)
		# if cached:
		# 	return cached

		endpoint = "SV/Machine/Address?"
		if filter_query:
			endpoint += f"{filter_query}"
		if sort_query:
			for k, v in sort_query:
				endpoint += f"&{k}={v}"

		try:
			response = icorp_api_get(endpoint)
			data = response.get("data", {}).get("address_machines", [])
			pagination = response.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				MachineAddress._total_count = total_records

			items = []
			machine_name = response.get("data", {}).get("name")  # Get machine name from API response

			for address in data:
				address_row = dict(address)
				address_row["address_id"] = str(address_row.pop("id", ""))
				address_row["machine_name"] = machine_name  # Set machine name for display
				address_row["name"] = frappe.generate_hash(length=10)
				items.append(address_row)

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineAddress.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
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
			frappe.log_error(frappe.get_traceback(), "MachineAddress.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass
