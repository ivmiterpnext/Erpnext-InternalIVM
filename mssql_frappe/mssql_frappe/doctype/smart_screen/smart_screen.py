# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.api_utils import headwind_api_request
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import ensure_meta_is_ready, set_attrs_from_dict


class SmartScreen(BaseVirtualDoctype):
	KEY_FIELD = "number"
	SORT_FIELD_MAP = { "name": KEY_FIELD }
	endpoint = None

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		try:
			ensure_meta_is_ready(self)

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

	@classmethod
	def get_list(cls, args=None):
		page_length = int(args.get("page_length") or 20)
		start = int(args.get("start") or 0)
		page = (start // page_length) + 1

		cache_key = f"smart_screen_list_cache_{page}_{page_length}_{args.get('filters')}"
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
			items = api_data_to_frappe_dict(devices, cls.KEY_FIELD)
			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SmartScreen.get_list error")
			return []

	@staticmethod
	def get_count(args=None, **kwargs):
		data = { "pageNum": 1, "pageSize": 1 }
		try:
			response = headwind_api_request("POST", "private/devices/search", data=data)
			return response.get("data", {}).get("devices", {}).get("total_items_count", 0)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SmartScreen.get_count error")
			return 0

	def get_indicator(self):
		color = (self.status_code or "gray").lower()
		label = self.status_code.capitalize() if self.status_code else "Unknown"
		return (label, color, {"status_code": self.status_code})
