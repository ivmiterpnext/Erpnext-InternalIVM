# Copyright (c) 2023, korecent and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class WarehouseRequest(Document):
	def get_title(self):
		"""Return formatted title for link fields"""
		if self.subject:
			return f"{self.name} - {self.subject}"
		return self.name
