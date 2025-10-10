# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import headwind_api_request
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import set_attrs_from_dict


class SmartScreen(Document):
	_total_count = None

	KEY_FIELD = "number"
	SORT_FIELD_MAP = { "name": "number" }

	_table_fieldnames = [] # Prevent frappe from trying to access non-existent table fields

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		try:
			endpoint = f"private/devices/number/{self.name}"
			item = headwind_api_request("GET", endpoint)
			data = item.get("data", {})

			if isinstance(data, list):
				if not data:
					return
				data = data[0]

			child_table_map = {
				"groups": "group_id" 
			}
			if "groups" in data:
				data["groups"] = [{"group_id": g["id"]} for g in data["groups"]]

			set_attrs_from_dict(self, data, child_table_map)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SmartScreen.load_from_db error")
			raise

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=30, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		cache_key = f"smart_screen_list_cache_{page}_{page_length}_{filters}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		data = {
			"pageNum": page,
			"pageSize": page_length
		}

		try:
			response = headwind_api_request("POST", "private/devices/search", data=data)
			devices = response.get("data", {}).get("devices", {}).get("items", [])
			total_records = response.get("data", {}).get("devices", {}).get("total_items_count", 0)

			if total_records is not None:
				SmartScreen._total_count = total_records

			items = api_data_to_frappe_dict(devices, SmartScreen.KEY_FIELD)

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SmartScreen.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if SmartScreen._total_count is not None:
			return SmartScreen._total_count

		data = { "pageNum": 1, "pageSize": 1 }
		try:
			response = headwind_api_request("POST", "private/devices/search", data=data)
			return response.get("data", {}).get("devices", {}).get("total_items_count", 0)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SmartScreen.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	def get_indicator(self):
		color = (self.status_code or "gray").lower()
		label = self.status_code.capitalize() if self.status_code else "Unknown"
		return (label, color, {"status_code": self.status_code})
