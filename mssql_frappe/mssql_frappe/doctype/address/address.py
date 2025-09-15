# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_id
from mssql_frappe.utils.api_utils import *
from mssql_frappe.utils.data_utils import set_attrs_from_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params


class Address(Document):
	def check_if_latest(self):
		pass  # Disable optimistic locking for virtual DocType

	def validate_set_only_once(self):
		pass # Disable "Set Only Once" validation for virtual DocType

	@property
	def _action(self):
		# Always return "save" if not set
		return getattr(self, "__action", "save")

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		try:
			endpoint = f"Address/GetById?Id={self.name}"
			item = icorp_api_get(endpoint)
			data = item.get("data", {})

			if isinstance(data, list):
				if not data:
					return
				data = data[0]

			set_attrs_from_dict(self, data)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Address.load_from_db error")
			raise

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

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
			endpoint = f"Address?ActiveStatus=All&page={page}&pageSize={page_length}"
			if filter_query:
				endpoint += f"&{filter_query}"

			result = icorp_api_get(endpoint)
			items = result.get("data", [])
			
			for item in items:
				address_parts = [
					item.get("address_line_one"),
					item.get("address_line_two"),
					item.get("address_line_three"),
					item.get("address_line_four"),
					item.get("city"),
					item.get("state_code"),
					item.get("country_code"),
					item.get("postal_code")
				]
				item["full_address"] = ", ".join([part for part in address_parts if part])

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
			frappe.log_error(frappe.get_traceback(), "Address.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		pass

	@staticmethod
	def get_stats(**kwargs):
		pass

