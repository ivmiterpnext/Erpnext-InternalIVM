import frappe

from ivm.support.utils import fetch_customer_name_and_contact

SUPPORT_ISSUE_TYPES = ['IT', 'Support', 'Receivable', 'Reconfiguration', 'Vending Management']


def on_update(doc, method):
    if doc.reference_doctype != "Issue":
        return

    try:
        attachments = doc.get_attachments()
        reference_name = frappe.get_all('Communication', filters={'reference_name': doc.reference_name}, fields=['reference_name'])
        # getting record matching to email received
        email = None
        if (doc.email_account):
            email = frappe.db.get_value(
                'Email Account', {'name': doc.email_account}, "name")

        if email:
            email_Account = frappe.get_doc("Email Account", email)
            # getting issue type from email account doctype
            issue_type = email_Account.imap_folder[0].custom_issue_type
            issue_name = frappe.get_doc("Issue", doc.reference_name)
            if issue_type in SUPPORT_ISSUE_TYPES:
                customer = fetch_customer_name_and_contact(doc.sender)
                if customer:
                    issue_name.customer = customer.get('customer_name')
                    issue_name.contact_name = customer.get('contact_name')
            issue_name.issue_type = issue_type
            if (len(reference_name) <= 1):
                issue_name.description = doc.content
            issue_name.save()
            if (attachments):
                file_urls = [url['file_url'] for url in attachments]
                for file_url in file_urls:
                    already_attached = frappe.db.exists('File', {
                        'file_url': file_url,
                        'attached_to_doctype': 'Issue',
                        'attached_to_name': doc.reference_name,
                    })
                    if already_attached:
                        continue
                    file = frappe.get_doc({
                        'doctype': 'File',
                        'is_private': 1,
                        'file_url': file_url,
                        'attached_to_doctype': 'Issue',
                        'attached_to_name': doc.reference_name
                    })
                    file.save()
            frappe.db.commit()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ivm.support.event_handlers.communication.on_update error")
