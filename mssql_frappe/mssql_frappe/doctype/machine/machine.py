# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import *
from mssql_frappe.utils.case_utils import api_items_to_frappe_dict
from mssql_frappe.utils.data_utils import set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params

_machine_total_count = None

class Machine(Document):
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
				
			endpoint = f"SV/Machine"
			response = icorp_api_post(endpoint, data)
			data = response.get("data")

			if not data or "id" not in data:
				frappe.throw("Failed to create Machine in external API: {}".format(response))
			self.name = str(data["id"])

			for k, v in data.items():
				setattr(self, k, v)

			if not frappe.db.exists("Machine Link", self.name):
				frappe.get_doc({
					"doctype": "Machine Link",
					"name": self.name,
					"id": self.name,
					"machine_name": self.machine_name
				}).insert(ignore_permissions=True)

			# self.clear_machine_hardware_config_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.db_insert error")
			raise

	def load_from_db(self):
		try:
			endpoint = f"SV/Machine/GetById?Id={self.name}"
			item = icorp_api_get(endpoint)
			machine_data = item.get("data", {})
			
			if isinstance(machine_data, list):
				if not machine_data:
					return
				machine_data = machine_data[0]

			child_table_map = {
				# parent field name : child field name(s)
				"agreement_fee_type_ids": "agreement_fee_type_id"
			}

			set_attrs_from_dict(self, machine_data, child_table_map)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.load_from_db error")
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

			# Keeps Machine Link doctype in sync
			frappe.db.set_value("Machine Link", self.name, "machine_name", self.machine_name)

			# self.clear_machine_hardware_config_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.db_update error")
			raise
		
	def delete(self):
		# This "deactivates" a machine rather than delete it outright
		try:
			endpoint = f"SV/Machine?Id={self.name}"
			response = icorp_api_delete(endpoint, {"id": self.name})

			# Keeps Machine Link doctype in sync
			frappe.delete_doc("Machine Link", self.name, force=True)

			return response
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.delete error")
			raise

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		global _machine_total_count

		page = (start // page_length) + 1
		filter_query = filters_to_query_params(filters)

		cache_key = f"machine_list_cache_{page}_{page_length}_{filter_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		try:
			endpoint = f"SV/Machine?page={page}&pageSize={page_length}"
			if filter_query:
				endpoint += f"&{filter_query}"
			result = icorp_api_get(endpoint) or {}

			items = result.get("data", []) or []
			pagination = result.get("pagination", {}) or {}
			total_records = pagination.get("total_records")
			if total_records is not None:
				_machine_total_count = int(total_records)

			ids = [str(r["id"]) for r in items if r.get("id") is not None]

			title_by_id = {}
			if ids:
				cached_rows = frappe.get_all(
					"Machine Link",
					filters={"name": ["in", ids]},
					fields=["name", "machine_name"]
				)
				title_by_id.update({
					row["name"]: (row["machine_name"] or row["name"])
					for row in cached_rows
				})

			rows = api_items_to_frappe_dict(
				items,
				key_field="id",
				title_field="machine_name",
				title_map=title_by_id
			)

			# (optional) expose extra columns in list view
			for i, r in enumerate(items):
				rows[i]["client_name"] = r.get("client_name")
				rows[i]["machine_status_type_description"] = r.get("machine_status_type_description")

			frappe.cache().set_value(cache_key, rows, expires_in_sec=300)
			return rows

		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.get_list error")
			return []


	@staticmethod
	def get_count(filters=None, **kwargs):
		global _machine_total_count
		if _machine_total_count is not None:
			return _machine_total_count
		try:
			endpoint = f"SV/Machine?page=1&pageSize=1"
			result = icorp_api_get(endpoint)
			pagination = result.get("pagination", {})
			total_records = pagination.get("total_records")
			if total_records is not None:
				_machine_total_count = int(total_records)
			return _machine_total_count
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass