"""
Service Quote detail page controller.
"""

import frappe

from ivm.client_portal.utils.signers import get_signer_row_for_user
from ivm.client_portal.utils.activity_log import log_quote_activity


def get_context(context):
    """
    Load Service Quote and prepare context for the detail page.

    Validates user has permission to view this quote, then logs a "View"
    event for audit purposes.
    """
    quote_name = frappe.form_dict.get("name")
    if not quote_name:
        raise frappe.PageNotFoundError

    try:
        quote_doc = frappe.get_doc("Service Quote", quote_name)
    except frappe.DoesNotExistError:
        raise frappe.PageNotFoundError

    signer_row = get_signer_row_for_user(quote_doc)
    if not signer_row:
        if frappe.session.user == "Guest":
            frappe.local.flags.redirect_location = "/login"
            raise frappe.Redirect
        else:
            raise frappe.PermissionError

    log_quote_activity(quote_doc, signer_row, "View Page")

    # Routed through our own endpoint before core download_pdf so downloads get logged.
    pdf_url = f"/api/method/ivm.client_portal.services.pdf.download_quote_pdf?service_quote={quote_name}"

    context.quote = quote_doc
    context.signer = signer_row
    context.pdf_url = pdf_url
    context.title = f"Service Quote {quote_name}"
