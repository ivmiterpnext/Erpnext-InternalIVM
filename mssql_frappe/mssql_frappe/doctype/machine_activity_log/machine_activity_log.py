# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype


class MachineActivityLog(BaseVirtualDoctype):
	KEY_FIELD = "id"
	SORT_FIELD_MAP = { "name": KEY_FIELD }

	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		raise NotImplementedError

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError
