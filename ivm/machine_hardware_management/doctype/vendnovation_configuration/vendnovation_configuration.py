# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.common.utils.base_virtual_doctype import BaseVirtualDoctype


class VendnovationConfiguration(BaseVirtualDoctype):
	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		raise NotImplementedError

	def db_update(self):
		pass

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(args=None, page_length=20, **kwargs):
		pass

	@staticmethod
	def get_count(*args, **kwargs):
		pass
