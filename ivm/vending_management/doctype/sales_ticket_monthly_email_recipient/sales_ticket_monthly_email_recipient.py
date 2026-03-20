# Copyright (c) 2026, IVM and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SalesTicketMonthlyEmailRecipient(Document):
	def before_save(self):
		"""Automatically populate contact_email from linked Contact if not set"""
		if self.contact and not self.contact_email:
			self.set_contact_email_from_contact()

	def set_contact_email_from_contact(self):
		"""Fetch email from the linked Contact's email_ids child table"""
		if not self.contact:
			return
		
		contact_doc = frappe.get_doc("Contact", self.contact)
		
		if hasattr(contact_doc, "email_ids") and contact_doc.email_ids:
			primary_email = None
			first_email = None
			
			for email in contact_doc.email_ids:
				if not first_email:
					first_email = email.name
				if getattr(email, "is_primary", False):
					primary_email = email.name
					break
			
			self.contact_email = primary_email or first_email
