# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import icorp_api_get, icorp_get_count
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES


class Address(Document):
	_total_count = None

	KEY_FIELD = "id"
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
		raise NotImplementedError

	def load_from_db(self):
		try:
			ensure_meta_is_ready(self)
			
			endpoint = f"Address/GetById?Id={self.name}"
			item = icorp_api_get(endpoint)
			data = item.get("data", {})

			set_attrs_from_dict(self, data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Address.load_from_db error")
			raise

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		filter_query = filters_to_query_params(filters)
		sort_query = build_sort_params(order_by, Address.SORT_FIELD_MAP) if order_by else []

		cache_key = f"address_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		try:
			endpoint = f"Address?ActiveStatus=All&page={page}&pageSize={page_length}"
			if filter_query:
				endpoint += f"&{filter_query}"
			if sort_query:
				for k, v in sort_query:
					endpoint += f"&{k}={v}"

			response = icorp_api_get(endpoint)
			data = response.get("data", [])
			pagination = response.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				Address._total_count = total_records

			# Combine address parts for full_address field
			for item in data:
				address_parts = [
					item.get("address_line_one"),
					item.get("address_line_two"),
					item.get("address_line_three"),
					item.get("address_line_four"),
					item.get("city"),
					item.get("state_code"),
					item.get("country_code"),
					item.get("postal_code")
				]
				item["full_address"] = ", ".join([part for part in address_parts if part])

			items = api_data_to_frappe_dict(
				data,
				key_field="id"
			)

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Address.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if Address._total_count is not None:
			return Address._total_count
		try:
			return icorp_get_count("Address", filters)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Address.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass
