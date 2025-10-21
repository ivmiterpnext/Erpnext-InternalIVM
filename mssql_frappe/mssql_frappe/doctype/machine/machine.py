# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from mssql_frappe.utils.api_utils import (icorp_api_put)
from mssql_frappe.utils.cache_util import clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict
from mssql_frappe.utils.data_utils import set_attrs_from_dict


class Machine(BaseVirtualDoctype):
	KEY_FIELD = "id"
	BOOL_FIELDS = ["has_smart_screen", "use_machine_timezone", "using_job_code", "allow_skip_job_code", "is_vend_return"]
	SORT_FIELD_MAP = {"name": KEY_FIELD, "creation": "createdDate", "machine_name": "machineName"}
	endpoint = "SV/Machine"

# Get List Overrides
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

# Load from DB Overrides
	def process_load_response(self, data):
		print("load data: ", data)
		# if data.get("id"):
		# 	self.name = str(data["id"])

		# if "name" in data:
		# 	data["machine_name"] = data["name"]

		child_table_map = {
			"agreement_fee_type_ids": "agreement_fee_type_id",
		}


		set_attrs_from_dict(self, data, child_table_map)

# Insert Overrides
	def prepare_insert_data(self, data):
		data["name"] = data.get("machine_name")

		if "time_zone_id" in data:
			data["time_zone_id"] = str(data["time_zone_id"])

		if hasattr(self, "agreement_fee_type_ids"):
			data["agreement_fee_type_ids"] = [
				int(row.agreement_fee_type_id)
				for row in getattr(self, "agreement_fee_type_ids", [])
				if hasattr(row, "agreement_fee_type_id") and row.agreement_fee_type_id
			]
		return data

	def process_insert_response(self, result):
		if "name" in result:
			result["machine_name"] = result.pop("name")

		if not frappe.db.exists("Machine Link", result.get("id")):
			frappe.get_doc({
				"doctype": "Machine Link",
				"name": result.get("id"),
				"id": result.get("id"),
				"machine_name": result.get("machine_name"),
			}).insert(ignore_permissions=True)

		clear_cache("machine_list_cache", "machine_count")

# Update Overrides
	def prepare_update_data(self, data):
		data["name"] = self.machine_name

		if "time_zone_id" in data:
			data["time_zone_id"] = str(data["time_zone_id"])

		print("data: ", data)
		return data

	def process_update_response(self, result):
		if "name" in result:
			result["machine_name"] = result.pop("name")

		self._sync_agreement_fee_types()

# Delete Overrides
	def delete(self):
		# "Deactivates" machines in ICORP, not delete
		result = super().delete()

		frappe.delete_doc("Machine Link", self.name, force=True)
		clear_cache("machine_list_cache", "machine_count")
		return result

# Helpers
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
