# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.api_utils import (icorp_api_post, icorp_api_get, icorp_api_put, icorp_api_delete, icorp_get_count)
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.data_utils import set_attrs_from_dict, ensure_meta_is_ready, build_sort_params
from mssql_frappe.utils.filter_utils import filters_to_query_params


class Machine(BaseVirtualDoctype):
	KEY_FIELD = "id"
	BOOL_FIELDS = ["has_smart_screen", "use_machine_timezone", "using_job_code",
					"allow_skip_job_code", "is_vend_return"]

	# Map Frappe list fields to API field names
	SORT_FIELD_MAP = {
		"name": KEY_FIELD,
		"creation": "createdDate",
		"machine_name": "machineName",
	}

	def pre_insert_data(self, data):
		data = convert_fields_to_bool(data, self.BOOL_FIELDS)
		data["name"] = data.get("machine_name")

		if "time_zone_id" in data:
			data["time_zone_id"] = str(data["time_zone_id"])
		return data

	def post_insert_response(self, payload):
		machine_id = str(payload.get("id") or "")
		if not machine_id:
			frappe.throw(f"Failed to create Machine in external API: {payload}")
		if "name" in payload:
			payload["machine_name"] = payload.pop("name")

		for k, v in payload.items():
			setattr(self, k, v)
		self.name = machine_id
	
		if not frappe.db.exists("Machine Link", self.name):
			frappe.get_doc({
				"doctype": "Machine Link",
				"name": self.name,
				"id": self.name,
				"machine_name": self.machine_name,
			}).insert(ignore_permissions=True)

		clear_cache("machine_list_cache", "machine_count")

	def post_process_loaded_data(self, data):
		# if data.get("id"):
		# 	self.name = str(data["id"])

		# if "name" in data:
		# 	data["machine_name"] = data["name"]

		child_table_map = {
			"agreement_fee_type_ids": "agreement_fee_type_id",
		}

		set_attrs_from_dict(self, data, child_table_map)

	def db_update(self):
		try:
			data = self.get_valid_dict()
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)
			data[self.KEY_FIELD] = self.name
			data["name"] = self.machine_name

			response = icorp_api_put("SV/Machine", data) or {}
			payload = response.get("data") or {}

			machine_id = str(payload.get("id") or "")
			if not machine_id:
				frappe.throw(f"Failed to update Machine in external API: {response}")

			if "name" in payload:
				payload["machine_name"] = payload.pop("name")

			self._sync_agreement_fee_types()

			for k, v in payload.items():
				setattr(self, k, v)
			self.name = machine_id

			frappe.db.set_value("Machine Link", self.name, "machine_name", self.machine_name)
			clear_cache("machine_list_cache", "machine_count")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.db_update error")
			raise

	def delete(self):
		# External system "deactivate"
		try:
			endpoint = f"SV/Machine?Id={self.name}"
			resp = icorp_api_delete(endpoint, {"id": self.name})
			frappe.delete_doc("Machine Link", self.name, force=True)
			return resp
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine.delete error")
			raise

	@classmethod
	def process_list_data(cls, data, args):
		ids = [str(r["id"]) for r in data if r.get("id") is not None]

		title_by_id = {}
		if ids:
			cached_rows = frappe.get_all(
				"Machine Link",
				filters={"name": ["in", ids]},
				fields=["name", "machine_name"],
			)
			title_by_id.update({
				row["name"]: (row["machine_name"] or row["name"])
				for row in cached_rows
			})

		return api_data_to_frappe_dict(
			data,
			cls.KEY_FIELD,
			title_field="machine_name",
			title_map=title_by_id,
		)

	@classmethod
	def get_count_from_api(cls, filters):
		return icorp_get_count("SV/Machine", filters)

	def _sync_agreement_fee_types(self):
		try:
			fee_type_ids = [
				int(row.agreement_fee_type_id)
				for row in getattr(self, "agreement_fee_type_ids", [])
				if hasattr(row, "agreement_fee_type_id") and row.agreement_fee_type_id
			]
			payload = {
				"id": int(self.name),
				"agreement_fee_type_ids": fee_type_ids,
			}

			return icorp_api_put("SV/Machine/FeeTypes", payload)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Machine._sync_agreement_fee_types error")
			raise
