from __future__ import annotations

import frappe
from frappe.model.document import Document


IT_SUPPORT = "IT_SUPPORT"
EMAIL_SOURCE = "Email"


class Ticket(Document):
	def before_insert(self) -> None:
		if not self.opened_on:
			self.opened_on = frappe.utils.now_datetime()

		if self.source == EMAIL_SOURCE and not self.business_area:
			self.business_area = IT_SUPPORT
