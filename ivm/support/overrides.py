import frappe
from frappe.email.doctype.email_account.email_account import EmailAccount


class CustomEmailAccount(EmailAccount):
    def send_auto_reply(self, communication, email):
        """Skip auto-reply after the first message in an existing thread (avoid reply loops)."""
        thread_count = frappe.db.count(
            "Communication",
            {
                "reference_doctype": communication.reference_doctype,
                "reference_name": communication.reference_name,
            },
        )
        if thread_count <= 1:
            super().send_auto_reply(communication, email)
