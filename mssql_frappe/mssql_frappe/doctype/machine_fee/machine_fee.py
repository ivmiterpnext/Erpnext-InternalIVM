# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype


class MachineFee(BaseVirtualDoctype):
	KEY_FIELD = "id"
	SORT_FIELD_MAP = { "name": KEY_FIELD }

	endpoint = "ClientContract/Fee/MachineFee"
