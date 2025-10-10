# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import icorp_api_post, icorp_api_get, icorp_api_put, icorp_api_delete, icorp_get_count
from mssql_frappe.utils.cache_util import clear_cache_by_prefix
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.data_utils import build_sort_params, set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params


class Machine(Document):
	_total_count = None

	KEY_FIELD = "id"
	BOOL_FIELDS = ["has_smart_screen", "use_machine_timezone", "using_job_code", "allow_skip_job_code", "is_vend_return"]
	SORT_FIELD_MAP = { "name": "id" }

	_table_fieldnames = [] # Prevent frappe from trying to access non-existent table fields

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
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)
			data["name"] = data.get("machine_name")

			response = icorp_api_post("SV/Machine", data)
			data = response.get("data") or {}

			machine_id = str(data.get("id") or "")
			if not machine_id:
				frappe.throw(f"Failed to create Machine in external API: {response}")

			if "name" in data:
				data["machine_name"] = data.pop("name")

			for k, v in data.items():
				setattr(self, k, v)
			self.name = machine_id

			if not frappe.db.exists("Machine Link", self.name):
				frappe.get_doc({
					"doctype": "Machine Link",
					"name": self.name,
					"id": self.name,
					"machine_name": self.machine_name,
				}).insert(ignore_permissions=True)

			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.db_insert error")
			raise

	def load_from_db(self):
		try:
			endpoint = f"SV/Machine/GetById?Id={self.name}"
			item = icorp_api_get(endpoint)
			machine_data = item.get("data", {}) or {}
			
			# if "name" in machine_data:
			# 	machine_data["machine_name"] = machine_data.pop("name")

			machine_name = frappe.db.get_value(
				"Machine Link",
				{"id": machine_data.get("id")},
				"machine_name"  # pass as a string, not a list
			)
			frappe.log_error(machine_data, "Machine.load_from_db error")

			if machine_name:
				machine_data["machine_name"] = machine_name

			child_table_map = { "agreement_fee_type_ids": "agreement_fee_type_id" }
			set_attrs_from_dict(self, machine_data, child_table_map)

			if machine_data.get("id"):
				self.name = str(machine_data["id"])
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.load_from_db error")
			raise

	def db_update(self):
		try:
			data = self.get_valid_dict()
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)
			data[self.KEY_FIELD] = self.name
			data["name"] = self.machine_name

			response = icorp_api_put("SV/Machine", data)
			data = response.get("data") or {}

			machine_id = str(data.get("id") or "")
			if not machine_id:
				frappe.throw(f"Failed to update Machine in external API: {response}")

			if "name" in data:
				data["machine_name"] = data.pop("name")

			self._sync_agreement_fee_types()

			for k, v in data.items():
				setattr(self, k, v)
			self.name = machine_id

			frappe.db.set_value("Machine Link", self.name, "machine_name", self.machine_name)
			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.db_update error")
			raise

	def delete(self):
		# This "deactivates" a machine rather than delete it
		try:
			endpoint = f"SV/Machine?Id={self.name}"
			response = icorp_api_delete(endpoint, {"id": self.name})

			frappe.delete_doc("Machine Link", self.name, force=True)
			return response
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.delete error")
			raise

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		filter_query = filters_to_query_params(filters)
		sort_query = build_sort_params(order_by, Machine.SORT_FIELD_MAP) if order_by else []

		cache_key = f"machine_list_cache_{page}_{page_length}_{filter_query}"
		cached = frappe.cache().get_value(cache_key)
		# if cached:
		# 	return cached

		endpoint = f"SV/Machine?page={page}&pageSize={page_length}"
		if filter_query:
			endpoint += f"&{filter_query}"
		if sort_query:
			for k, v in sort_query:
				endpoint += f"&{k}={v}"

		try:
			response = icorp_api_get(endpoint) or {}
			data = response.get("data", []) or []
			pagination = response.get("pagination", {}) or {}
			total_records = pagination.get("total_records")

			if total_records is not None:
				Machine._total_count = total_records

			ids = [str(r["id"]) for r in data if r.get("id") is not None]

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

			items = api_data_to_frappe_dict(
				data,
				Machine.KEY_FIELD,
				title_field="machine_name",
				title_map=title_by_id
			)

			frappe.cache().set_value(cache_key, items, expires_in_sec=300)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if Machine._total_count is not None:
			return Machine._total_count
		try:
			return icorp_get_count("SV/Machine", filters)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	@staticmethod
	def clear_cache():
		Machine._total_count = None
		clear_cache_by_prefix("machine_list_cache")

	def _sync_agreement_fee_types(self):
		try:
			fee_type_ids = [
				int(row.agreement_fee_type_id)
				for row in getattr(self, "agreement_fee_type_ids", [])
				if hasattr(row, "agreement_fee_type_id")
			]

			payload = {
				"id": int(self.name),
				"agreement_fee_type_ids": fee_type_ids
			}

			endpoint = "SV/Machine/FeeTypes"
			response = icorp_api_put(endpoint, payload)

			return response
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine._sync_agreement_fee_types error")
			raise
