# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.azure_api_utils import azure_api_get
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, api_items_to_frappe_dict
from mssql_frappe.utils.filter_utils import match_filter


class BoardType(Document):
	_api_data_cache = None

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		try:
			url = f"https://dev.icorpapi.ivminc.com/SV/BoardType/GetByCode?Code={self.name}"
			data = azure_api_get(url)
			item = dict_keys_to_snake_case(data.get("data", {}))
			for k, v in item.items():
				if not isinstance(v, (str, int, float, bool, type(None))):
					v = str(v)
				setattr(self, k, v)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "BoardType.load_from_db error")
			raise

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		try:
			url = "https://dev.icorpapi.ivminc.com/SV/BoardType"
			data = azure_api_get(url)
			items = data.get("data", [])

			if kwargs.get("as_list"):
				return [(item["code"], item["description"], item["description"]) for item in items]
			return api_items_to_frappe_dict(items, name_field="code")

		except Exception:
			frappe.log_error(frappe.get_traceback(), "BoardType.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		try:
			if BoardType._api_data_cache is not None:
				items = BoardType._api_data_cache
			else:
				url = "https://dev.icorpapi.ivminc.com/SV/BoardType"
				data = azure_api_get(url)
				items = data.get("data", [])
				BoardType._api_data_cache = items
			return len(items)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "BoardType.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	@staticmethod
	def clear_api_cache():
		BoardType._api_data_cache = None

@frappe.whitelist()
def get_board_type_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
    return BoardType.get_list(filters, page_length, start, order_by, **kwargs)
