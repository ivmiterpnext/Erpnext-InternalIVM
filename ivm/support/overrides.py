import frappe
from frappe import _
from frappe.email.doctype.email_account.email_account import EmailAccount
from frappe.utils.jinja import render_template


class CustomEmailAccount(EmailAccount):
    def send_auto_reply(self, communication, email):
        """Send auto reply if set."""
        from frappe.core.doctype.communication.email import set_incoming_outgoing_accounts

        if self.enable_auto_reply:

            set_incoming_outgoing_accounts(communication)

            unsubscribe_message = (self.send_unsubscribe_message and _(
                "Leave this conversation")) or ""
            issue_name = frappe.get_all('Communication', filters={
                                        'reference_name': communication.reference_name}, fields=['reference_name'])
            if (len(issue_name) <= 1):
                frappe.sendmail(
                    recipients=[email.from_email],
                    sender=self.email_id,
                    reply_to=communication.incoming_email_account,
                    subject=" ".join([_("Re:"), communication.subject]),
                    content=render_template(
                        self.auto_reply_message or "", communication.as_dict())
                    or frappe.get_template("templates/emails/auto_reply.html").render(communication.as_dict()),
                    reference_doctype=communication.reference_doctype,
                    reference_name=communication.reference_name,
                    # send back the Message-Id as In-Reply-To
                    in_reply_to=email.mail.get(
                        "Message-Id"),
                    unsubscribe_message=unsubscribe_message,
                )
