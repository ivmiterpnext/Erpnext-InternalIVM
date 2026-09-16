"""
Portal-facing PDF download endpoint for Service Quote.

Wraps Frappe's core frappe.utils.print_format.download_pdf so we can log a
"Download PDF" event server-side on every actual download request, while
still delegating the real PDF generation to core (same params the portal
page previously called directly).
"""

import frappe

from ivm.client_portal.utils.signers import get_signer_row_for_user
from ivm.client_portal.utils.activity_log import log_quote_activity

PRINT_FORMAT = "Service Quote Client PDF"


@frappe.whitelist()
def download_quote_pdf(service_quote):
    """
    Validate the current user is an authorized signer for this Service
    Quote, log a "Download PDF" event, then stream the PDF via core.
    """
    quote_doc = frappe.get_doc("Service Quote", service_quote)

    signer_row = get_signer_row_for_user(quote_doc)
    if not signer_row:
        frappe.throw(
            "You are not authorized to download this Service Quote.",
            exc=frappe.PermissionError,
        )

    log_quote_activity(quote_doc, signer_row, "View PDF")

    from frappe.utils.print_format import download_pdf

    return download_pdf(
        doctype="Service Quote",
        name=service_quote,
        format=PRINT_FORMAT,
        doc=quote_doc,
        pdf_generator="chrome",
    )
