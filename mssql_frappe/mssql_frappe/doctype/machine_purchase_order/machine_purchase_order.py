# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.api_utils import icorp_api_post, icorp_api_get, icorp_api_put, icorp_api_delete, icorp_get_count
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params, replace_machine_id_with_name


class MachinePurchaseOrder(BaseVirtualDoctype):	
	KEY_FIELD = "id"
	endpoint = "PurchaseOrder/Machines"

	def db_insert(self, *args, **kwargs):
		try:
			data = self.get_valid_dict()

			endpoint = "PurchaseOrder/Machine"
			response = icorp_api_post(endpoint, data)
			data = response.get("data")

			if not data or not data.get("id"):
				frappe.throw(f"Failed to create Machine Purchase Order in external API: {response}")

			self.name = str(data["id"])
			for k, v in data.items():
				setattr(self, k, v)

			# self.clear_machine_hardware_config_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.db_insert error")
			raise

	def db_update(self):
		try:
			data = self.get_valid_dict()
			data["id"] = data.pop("name")

			endpoint = "PurchaseOrder/Machine"
			response = icorp_api_put(endpoint, data)
			data = response.get("data")

			if not data or "id" not in data:
				frappe.throw(f"Failed to create Machine Purchase Order in external API: {response}")

			self.name = str(data["id"])
			for k, v in data.items():
				setattr(self, k, v)

			self.clear_machine_hardware_config_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.db_update error")
			raise

	@classmethod
	def preprocess_filters(cls, filters):
		if filters:
			filters = replace_machine_id_with_name(filters)
		return filters

	def delete(self):
		try:
			endpoint = f"PurchaseOrder/Machine/Delete?Id={self.name}"
			response = icorp_api_delete(endpoint, {"id": self.name})
			return response
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.delete error")
			raise

	@classmethod
	def get_count_from_api(cls, filters):
		return icorp_get_count(cls.endpoint, filters)
		