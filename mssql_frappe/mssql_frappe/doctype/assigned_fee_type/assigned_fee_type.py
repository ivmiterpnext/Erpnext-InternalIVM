# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class AssignedFeeType(Document):
	def db_insert(self, *args, **kwargs):
		pass

	def load_from_db(self):
		raise NotImplementedError

	def db_update(self):
		pass

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, **kwargs):
		pass

	@staticmethod
	def get_count(filters=None, **kwargs):
		pass

	@staticmethod
	def get_stats(**kwargs):
		pass
