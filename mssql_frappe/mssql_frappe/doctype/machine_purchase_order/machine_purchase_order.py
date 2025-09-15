# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_id
from mssql_frappe.utils.api_utils import *
from mssql_frappe.utils.case_utils import api_items_to_frappe_dict
from mssql_frappe.utils.data_utils import set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params


class MachinePurchaseOrder(Document):
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

			endpoint = f"PurchaseOrder/Machine"
			response = icorp_api_post(endpoint, data)
			data = response.get("data")

			if not data or "id" not in data:
				frappe.throw("Failed to create Machine Purchase Order in external API: {}".format(response))
			self.name = str(data["id"])

			for k, v in data.items():
				setattr(self, k, v)

			# self.clear_machine_hardware_config_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.db_insert error")
			raise

	def load_from_db(self):
		try:
			endpoint = f"PurchaseOrder/Machine/GetById?Id={self.name}"
			item = icorp_api_get(endpoint)
			data = item.get("data", {})

			if isinstance(data, list):
				if not data:
					return
				data = data[0]

			set_attrs_from_dict(self, data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.load_from_db error")
			raise

	def db_update(self):
		try:
			data = self.get_valid_dict()

			endpoint = f"PurchaseOrder/Machine"
			response = icorp_api_put(endpoint, data)
			data = response.get("data")

			if not data or "id" not in data:
				frappe.throw("Failed to create Machine Purchase Order in external API: {}".format(response))

			self.name = str(data["id"])
			for k, v in data.items():
				setattr(self, k, v)

			# self.clear_machine_hardware_config_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.db_update error")
			raise

	def delete(self):
		try:
			endpoint = f"PurchaseOrder/Machine/Delete?Id={self.name}"
			response = icorp_api_delete(endpoint, {"id": self.name})
			return response
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.delete error")
			raise

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		global _machine_purchase_order_total_count
		page = (start // page_length) + 1

		if filters:
			new_filters = []
			for f in filters:
				if (isinstance(f, (list, tuple)) and len(f) >= 4 and f[1] == "machine_id"):
					machine_name = get_machine_name_from_id(f[3])
					if machine_name:
						# Replace machine_id filter with machine_name filter
						new_filters.append((f[0], "machine_name", f[2], machine_name))
					else:
						new_filters.append(f)
				else:
					new_filters.append(f)

			filters = new_filters

		filter_query = filters_to_query_params(filters)

		cache_key = f"mhc_list_cache_{page}_{page_length}_{filter_query}_{order_by or ''}"
		cached = frappe.cache().get_value(cache_key)
		# if cached:
		#   return cached

		try:
			endpoint = f"PurchaseOrder/Machines?ActiveStatus=All&page={page}&pageSize={page_length}"
			if filter_query:
				endpoint += f"&{filter_query}"

			result = icorp_api_get(endpoint)
			items = result.get("data", [])

			pagination = result.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				_machine_purchase_order_total_count = int(total_records)

			value = api_items_to_frappe_dict(
				items,
				key_field="id"
			)

			frappe.cache().set_value(cache_key, value, expires_in_sec=300)
			return value
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		pass

	@staticmethod
	def get_stats(**kwargs):
		pass

