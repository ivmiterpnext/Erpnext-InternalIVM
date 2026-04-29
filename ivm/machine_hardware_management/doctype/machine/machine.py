# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from ivm.machine_hardware_management.utils.base_virtual_doctype import BaseVirtualDoctype
from ivm.machine_hardware_management.utils.api_utils import icorp_api_put
from ivm.machine_hardware_management.utils.case_utils import api_data_to_frappe_dict
from ivm.machine_hardware_management.utils.data_utils import set_attrs_from_dict


class Machine(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = ["has_smart_screen", "use_machine_timezone", "using_job_code", "allow_skip_job_code", "is_vend_return"]
	FIELD_MAP = {"name": "id", "machine_name": "name"}
	endpoint = "SV/Machine"

# Get List Overrides
	@classmethod
	def process_list_response(cls, data, args):
		for row in data:
			if "name" in row:
				row["machine_name"] = row["name"]
			if "client_name" in row:
				row["client_id"] = row["client_name"]
			if "location_name" in row:
				row["location_id"] = row["location_name"]
			if "machine_status_type_description" in row:
				row["machine_status_type_code"] = row["machine_status_type_description"]
			if "machine_type_name" in row:
				row["machine_type_id"] = row["machine_type_name"]


		return api_data_to_frappe_dict(
			data,
			cls.FIELD_MAP["name"]
		)

# Load from DB Overrides
	def process_load_response(self, data):
		if data.get("id"):
			self.name = str(data["id"])
			self.machine_id = str(data["id"])
		if "name" in data:
			data["machine_name"] = data["name"]
		if "modified_date" in data:
			data["modified"] = data["modified_date"]

		child_table_map = {
			"agreement_fee_type_ids": "agreement_fee_type_id",
		}

		set_attrs_from_dict(self, data, child_table_map)

# Insert Overrides
	def prepare_insert_data(self, data):
		data["name"] = data.get("machine_name")

		if "time_zone_id" in data:
			data["time_zone_id"] = str(data["time_zone_id"])

		return data

	def process_insert_response(self, data):
		if "name" in data:
			data["machine_name"] = data.pop("name")

		self._sync_agreement_fee_types()

		if not frappe.db.exists("Machine Link", data.get("id")):
			frappe.get_doc({
				"doctype": "Machine Link",
				"name": data.get("id"),
				"id": data.get("id"),
				"machine_name": data.get("machine_name"),
			}).insert(ignore_permissions=True)

# Update Overrides
	def prepare_update_data(self, data):
		data["id"] = self.name
		data["name"] = self.machine_name

		if "time_zone_id" in data:
			data["time_zone_id"] = str(data["time_zone_id"])

		print("data: ", data)
		return data

	def process_update_response(self, data):
		if "name" in data:
			data["machine_name"] = data.pop("name")
		if "modified_date" in data:
			data["modified"] = data["modified_date"]

		self._sync_agreement_fee_types()

# Delete Overrides
	def delete(self):
		# "Deactivates" machines in ICORP, not delete
		result = super().delete()

		frappe.delete_doc("Machine Link", self.name, force=True)
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
				"created_by": frappe.session.user if hasattr(frappe, "session") else "system-frappe"
			}

			return icorp_api_put("SV/Machine/FeeTypes", payload)
		except Exception as e:
			frappe.log_error(f"{e}\n{frappe.get_traceback()}", "Machine._sync_agreement_fee_types error")
			raise
