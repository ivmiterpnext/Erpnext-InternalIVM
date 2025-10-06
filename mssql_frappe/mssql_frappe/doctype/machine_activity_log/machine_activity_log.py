# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document

from mssql_frappe.utils.api_utils import icorp_api_get, icorp_get_count
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache_by_prefix
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import build_sort_params
from mssql_frappe.utils.filter_utils import filters_to_query_params


class MachineActivityLog(Document):
	_total_count = None

	KEY_FIELD = "id"
	SORT_FIELD_MAP = { "name": "id" }

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		raise NotImplementedError

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=30, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		filter_query = filters_to_query_params(filters)
		sort_query = build_sort_params(order_by, MachineActivityLog.SORT_FIELD_MAP) if order_by else []

		cache_key = f"machine_activity_log_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		endpoint = f"SV/MachineActivityLog?page={page}&pageSize={page_length}"
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
				MachineActivityLog._total_count = total_records

			items = api_data_to_frappe_dict(data, MachineActivityLog.KEY_FIELD)

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineActivityLog.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if MachineActivityLog._total_count is not None:
			return MachineActivityLog._total_count
		try:
			return icorp_get_count("SV/MachineActivityLog", filters)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineActivityLog.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	@staticmethod
	def clear_cache():
		MachineActivityLog._total_count = None
		clear_cache_by_prefix("machine_activity_log_list_cache")
