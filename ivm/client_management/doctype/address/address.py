# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.ivm.utils.base_virtual_doctype import BaseVirtualDoctype
from ivm.ivm.utils.case_utils import api_data_to_frappe_dict


class Address(BaseVirtualDoctype):
	FIELD_MAP = { "name": "id" }

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@classmethod
	def get_list_endpoint(cls, page, page_length, filter_query, sort_query):
		endpoint = f"Address?ActiveStatus=All&page={page}&pageSize={page_length}"
		if filter_query:
			endpoint += f"&{filter_query}"
		if sort_query:
			for k, v in sort_query:
				endpoint += f"&{k}={v}"
		return endpoint

	@classmethod
	def process_list_data(cls, data, args):
		# Combine address parts for full_address field
		for item in data:
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
		return api_data_to_frappe_dict(data, key_field=cls.FIELD_MAP["name"])
