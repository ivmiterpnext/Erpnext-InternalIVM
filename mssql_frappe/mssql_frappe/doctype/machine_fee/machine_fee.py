# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.api_utils import icorp_api_delete, icorp_api_get, icorp_api_post, icorp_api_put, icorp_get_count
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params


class MachineFee(BaseVirtualDoctype):
	KEY_FIELD = "id"
	SORT_FIELD_MAP = { "name": "id" }
	endpoint = "ClientContract/Fee/MachineFee"

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

			clear_cache("machine_fee_list_cache", "machine_fee_count")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineFee.db_insert error")
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

			clear_cache("machine_fee_list_cache", "machine_fee_count")
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

	@classmethod
	def get_count_from_api(cls, filters):
		# Use the icorp_get_count utility for this endpoint
		return icorp_get_count(cls.endpoint, filters)
