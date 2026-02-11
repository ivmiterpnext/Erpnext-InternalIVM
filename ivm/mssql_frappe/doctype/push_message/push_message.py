# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.mssql_frappe.utils.api_utils import headwind_api_request
from ivm.mssql_frappe.utils.case_utils import api_data_to_frappe_dict


class PushMessage(Document):
	API_TYPE = "headwind"
	FIELD_MAP = { "name": "id" }

	def db_insert(self, *args, **kwargs):
		try:
			data = self.get_valid_dict()
			data["MessageType"] = "Keystone"
			data["scope"] = "device"

			endpoint = "plugins/push/private/send"
			response = headwind_api_request("POST", endpoint, data=data)

			data = response.get("data")

			if not data or not data.get(self.FIELD_MAP["name"]):
				frappe.throw(f"Failed to send Push Message in external API: {response}")

			self.name = str(data[self.FIELD_MAP["name"]])
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

	@classmethod
	def get_list(cls, args=None):
		page_length = int(args.get("page_length") or 30)
		start = int(args.get("start") or 0)
		page = (start // page_length) + 1
		filters = args.get("filters")

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
			response = headwind_api_request("POST", "plugins/push/private/search", data=data)
			data = response.get("data", {}).get("items", [])
			items = api_data_to_frappe_dict(data, cls.FIELD_MAP["name"])
			for item in items:
				if "name" not in item:
					if cls.FIELD_MAP["name"] in item:
						item["name"] = str(item[cls.FIELD_MAP["name"]])
					else:
						item["name"] = ""
						
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
