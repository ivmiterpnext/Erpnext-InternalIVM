from __future__ import annotations

import frappe
from frappe.model.document import Document


class TicketActivity(Document):
	def before_insert(self) -> None:
		if not self.occurred_on:
			self.occurred_on = frappe.utils.now_datetime()
