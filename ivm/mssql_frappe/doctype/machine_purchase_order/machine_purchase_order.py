# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype
from ivm.mssql_frappe.utils.filter_utils import replace_machine_id_with_name, frappe_filters_to_dict
from ivm.mssql_frappe.utils.data_utils import set_attrs_from_dict


class MachinePurchaseOrder(BaseVirtualDoctype):
	API_TYPE = "icorp"
	endpoint = "PurchaseOrder/Machines"
	FIELD_MAP = {"name": "id"}

# Get List Overrides
	@classmethod
	def build_list_api_params(cls, args):
		# Only filters, no page/pageSize/sort
		filters = cls.preprocess_filters(args.get("filters"))
		params = frappe_filters_to_dict(filters, field_map=getattr(cls, "FIELD_MAP", {}))
		return params

	@classmethod
	def preprocess_filters(cls, filters):
		if filters:
			filters = replace_machine_id_with_name(filters)
		return filters

	@classmethod
	def process_list_response(cls, data, args):
		for row in data:
			if "name" in row:
				row["machine_name"] = row["name"]
			if "id" in row:
				row["name"] = str(row["id"])
		return data

# Load from DB Overrides
	def get_load_endpoint(self):
		return f"PurchaseOrder/Machine/GetById?Id={self.name}"

	def process_load_response(self, data):
		if data.get("id"):
			self.name = str(data["id"])
		if "name" in data:
			data["machine_name"] = data["name"]
		set_attrs_from_dict(self, data)

# Insert Overrides
	def prepare_insert_data(self, data):
		data["name"] = data.get("machine_name")
		return data

	def process_insert_response(self, data):
		if "name" in data:
			data["machine_name"] = data.pop("name")
		if "id" in data:
			self.name = str(data["id"])
		set_attrs_from_dict(self, data)

# Update Overrides
	def prepare_update_data(self, data):
		data["id"] = self.name
		data["name"] = self.machine_name
		return data

	def process_update_response(self, data):
		if "name" in data:
			data["machine_name"] = data.pop("name")
		if "id" in data:
			self.name = str(data["id"])
		set_attrs_from_dict(self, data)
