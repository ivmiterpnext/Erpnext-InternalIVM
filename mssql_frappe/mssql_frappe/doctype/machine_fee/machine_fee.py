# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import icorp_api_delete, icorp_api_get, icorp_api_post, icorp_api_put, icorp_get_count
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache_by_prefix
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params


class MachineFee(Document):
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
		try:
			data = self.get_valid_dict()
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)

			endpoint = "ClientContract/Fee/MachineFee"
			response = icorp_api_post(endpoint, data)
			data = response.get("data")

			if not data or not data.get(self.KEY_FIELD):
				frappe.throw(f"Failed to create Machine Fee in external API: {response}")

			self.name = str(data[self.KEY_FIELD])
			for k, v in data.items():
				setattr(self, k, v)

			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.db_insert error")
			raise

	def load_from_db(self):
		try:
			ensure_meta_is_ready(self)
			
			endpoint = f"ClientContract/Fee/MachineFee/GetById?Id={self.name}"
			item = icorp_api_get(endpoint)
			data = item.get("data", {})

			set_attrs_from_dict(self, data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.load_from_db error")
			raise

	def db_update(self):
		try:
			data = self.get_valid_dict()
			data[self.KEY_FIELD] = data.pop("name")
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)

			endpoint = "ClientContract/Fee/MachineFee"
			response = icorp_api_put(endpoint, data)
			data = response.get("data")

			if not data or self.KEY_FIELD not in data:
				frappe.throw(f"Failed to create Machine Fee in external API: {response}")

			self.name = str(data[self.KEY_FIELD])
			for k, v in data.items():
				setattr(self, k, v)

			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.db_update error")
			raise

	def delete(self):
		try:
			endpoint = f"ClientContract/Fee/MachineFee?Id={self.name}"
			return icorp_api_delete(endpoint)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.delete error")
			raise

	@staticmethod
	def get_list(filters=None, page_length=30, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		filter_query = filters_to_query_params(filters)
		sort_query = build_sort_params(order_by, MachineFee.SORT_FIELD_MAP) if order_by else []

		cache_key = f"machine_fee_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		endpoint = "ClientContract/Fee/MachineFee?"
		if filter_query:
			endpoint += f"&{filter_query}"
		if sort_query:
			for k, v in sort_query:
				endpoint += f"&{k}={v}"

		try:
			response = icorp_api_get(endpoint)
			data = response.get("data", [])
			pagination = response.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				MachineFee._total_count = total_records

			items = api_data_to_frappe_dict(data, MachineFee.KEY_FIELD)

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if MachineFee._total_count is not None:
			return MachineFee._total_count
		try:
			return icorp_get_count("ClientContract/Fee/MachineFee", filters)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	@staticmethod
	def clear_cache():
		MachineFee._total_count = None
		clear_cache_by_prefix("machine_fee_list_cache")
