# Copyright (c) 2026, IVM and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SupportTicket(Document):
    def autoname(self):
        """Set custom name based on linked Issue"""
        if self.issue:
            issue = frappe.get_doc('Issue', self.issue)
            self.name = f"{self.issue} - {issue.subject}"

        else:
            # Fallback to default naming if no issue linked
            self.name = frappe.generate_hash(length=10)
