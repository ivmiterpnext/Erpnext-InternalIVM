# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.azure_api_utils import azure_api_get
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, api_items_to_frappe_dict
from mssql_frappe.utils.filter_utils import match_filter, apply_multi_field_sort

class BoardConnection(Document):
	
	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		try:
			url = f"https://dev.icorpapi.ivminc.com/SV/BoardConnection/GetById?Id={self.name}"
			data = azure_api_get(url)
			item = dict_keys_to_snake_case(data.get("data", {}))
			# Map name to connection_name for display
			original_api_name = item.get('name')
			if 'id' in item:
				item['name'] = str(item['id'])
			if original_api_name is not None:
				item['connection_name'] = original_api_name
			for k, v in item.items():
				# Always cast *_id fields and name to string
				if k == 'id' or k.endswith('_id') or k == 'name':
					v = str(v) if v is not None else ''
				elif not isinstance(v, (str, int, float, bool, type(None))):
					v = str(v)
				setattr(self, k, v)
		except Exception:
			frappe.log_error(frappe.get_traceback()),

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		try:
			url = "https://dev.icorpapi.ivminc.com/SV/BoardConnection"
			data = azure_api_get(url)
			items = []
			for item in data.get("data", []):
				item = dict_keys_to_snake_case(item)
				# Save the original connection name
				if "name" in item:
					item["connection_name"] = item["name"]
				items.append(item)
			return api_items_to_frappe_dict(items, name_field="id")

			# if filters:
			#     for flt in filters:
			#         result = [item for item in result if match_filter(item, flt)]
					
			# result = apply_multi_field_sort(result, order_by)
			# return result
			
		except Exception:
			frappe.log_error(frappe.get_traceback(), "BoardConnection.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		try:
			url = f"https://dev.icorpapi.ivminc.com/SV/BoardConnection"
			data = azure_api_get(url)
			items = data.get("data", [])
			return len(items)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "BoardConnection.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass


@frappe.whitelist()
def get_board_connection_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
    return BoardConnection.get_list(filters, page_length, start, order_by, **kwargs)