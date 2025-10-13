# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import icorp_api_post, icorp_api_get, icorp_api_put, icorp_api_delete, icorp_get_count
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params, replace_machine_id_with_name


class MachinePurchaseOrder(Document):
	_total_count = None

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

	def load_from_db(self):
		try:
			ensure_meta_is_ready(self)
			
			endpoint = f"PurchaseOrder/Machine/GetById?Id={self.name}"
			response = icorp_api_get(endpoint)
			data = response.get("data", {})

			set_attrs_from_dict(self, data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.load_from_db error")
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
		page = (start // page_length) + 1

		if filters:
			filters = replace_machine_id_with_name(filters)
		filter_query = filters_to_query_params(filters)

		sort_field_map = {
			"name": "id",
		}
		sort_query = build_sort_params(order_by, sort_field_map=sort_field_map) if order_by else []

		cache_key = f"mhc_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		try:
			endpoint = f"PurchaseOrder/Machines?ActiveStatus=All&page={page}&pageSize={page_length}"
			if filter_query:
				endpoint += f"&{filter_query}"
			if sort_query:
				for k, v in sort_query:
					endpoint += f"&{k}={v}"

			response = icorp_api_get(endpoint)
			data = response.get("data", [])
			pagination = response.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				MachinePurchaseOrder._total_count = total_records

			items = api_data_to_frappe_dict(
				data,
				key_field="id"
			)

			frappe.cache().set_value(cache_key, items, expires_in_sec=300)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if MachinePurchaseOrder._total_count is not None:
			return MachinePurchaseOrder._total_count
		try:
			return icorp_get_count("PurchaseOrder/Machines", filters)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachinePurchaseOrder.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass
