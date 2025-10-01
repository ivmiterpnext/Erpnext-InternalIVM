# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from warnings import filters
import frappe
from frappe.model.document import Document

from mssql_frappe.utils.api_utils import headwind_api_request
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict


class PushMessage(Document):
	_total_count = None

	KEY_FIELD = "id"
	SORT_FIELD_MAP = { "name": "id" }

	def db_insert(self, *args, **kwargs):
		try:
			data = self.get_valid_dict()
			data["MessageType"] = "Keystone"
			data["scope"] = "device"

			endpoint = "plugins/push/private/send"
			response = headwind_api_request("POST", endpoint, data=data)

			data = response.get("data")

			if not data or not data.get(self.KEY_FIELD):
				frappe.throw(f"Failed to send Push Message in external API: {response}")

			self.name = str(data[self.KEY_FIELD])
			for k, v in data.items():
				setattr(self, k, v)

			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "PushMessage.db_insert error")
			raise
	def load_from_db(self):
		raise NotImplementedError

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=30, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		cache_key = f"push_message_list_cache_{page}_{page_length}_{filters}"
		cached = frappe.cache().get_value(cache_key)
		# if cached:
		# 	return cached

		device_filter = None
		if isinstance(filters, list):
			for f in filters:
				if isinstance(f, (list, tuple)) and len(f) >= 4 and f[1] == "device_number" and f[2] == "=":
					device_filter = f[3]
					break
		elif isinstance(filters, dict) and "device_number" in filters and filters["device_number"]:
			device_filter = filters["device_number"]

		data = {
			"pageNum": page,
			"pageSize": page_length
		}
		if device_filter:
			data["deviceFilter"] = device_filter

		try:
			print("PushMessage.get_list data:", data)
			response = headwind_api_request("POST", "plugins/push/private/search", data=data)
			data = response.get("data", {}).get("items", [])
			total_records = response.get("data", {}).get("total_items_count", 0)

			if total_records is not None:
				PushMessage._total_count = total_records

			items = api_data_to_frappe_dict(data, PushMessage.KEY_FIELD)

			for item in items:
				if "name" not in item:
					if PushMessage.KEY_FIELD in item:
						item["name"] = str(item[PushMessage.KEY_FIELD])
					else:
						item["name"] = ""

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "PushMessage.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		device_filter = None
		if isinstance(filters, list):
			for f in filters:
				if isinstance(f, (list, tuple)) and len(f) >= 4 and f[1] == "device_number" and f[2] == "=":
					device_filter = f[3]
					break
		elif isinstance(filters, dict) and "device_number" in filters and filters["device_number"]:
			device_filter = filters["device_number"]

		data = {
			"pageNum": 1,
			"pageSize": 1
		}
		if device_filter:
			data["deviceFilter"] = device_filter

		try:
			response = headwind_api_request("POST", "plugins/push/private/search", data=data)
			return response.get("data", {}).get("total_items_count", 0)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "PushMessage.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

