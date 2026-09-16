"""
Compute and update Service Quote status based on signer responses.
"""

import frappe
from frappe.utils import now_datetime


def resolve_signer_response(quote_doc, signer_row_name, response, typed_name, ip, reason=None):
    """
    Record a signer's response and update the parent quote's status.

    Args:
        quote_doc: Service Quote document object
        signer_row_name: Child row name of the signer
        response: "Accepted" or "Declined"
        typed_name: Name typed by the signer
        ip: IP address of the request
        reason: Optional free-text reason, only meaningful when response == "Declined"
    """
    signer_contact = frappe.db.get_value(
        "Service Quote Signer",
        signer_row_name,
        ["contact"],
        as_dict=True,
    )
    contact_name = signer_contact.contact if signer_contact else None

    # Update signer row
    frappe.db.set_value(
        "Service Quote Signer",
        signer_row_name,
        {
            "accepted_name": typed_name,
            "status": response,
            "accepted_on": now_datetime(),
            "accepted_ip": ip,
            "acceptance_statement_snapshot": quote_doc.terms,
        },
    )

    # Log to the unified Service Quote Activity Log audit trail (View Page /
    # View PDF / Accepted / Declined all live in one place). response is
    # always "Accepted" or "Declined" here, matching that doctype's
    # event_type options exactly. reason is only populated on decline.
    from ivm.client_portal.utils.activity_log import log_quote_activity

    log_quote_activity(quote_doc, frappe._dict(contact=contact_name), response, reason=reason)

    # Reload signer statuses from DB
    signers = frappe.get_all(
        "Service Quote Signer",
        filters={"parent": quote_doc.name},
        fields=["status"],
    )

    # Compute new parent status
    statuses = [s.status for s in signers]

    # Business rule: require all signers to accept if there's more than one signer
    requires_all = len(statuses) > 1

    if "Declined" in statuses:
        new_status = "Needs Rep Review"
    elif not requires_all:
        # If not requiring all signers, accept as soon as any signer accepts
        if "Accepted" in statuses:
            new_status = "Accepted"
        else:
            new_status = quote_doc.status  # No change, still Sent
    elif all(s == "Accepted" for s in statuses):
        # If requiring all signers, only accept when all have accepted
        new_status = "Accepted"
    elif "Accepted" in statuses:
        # Some accepted but not all, and all signers required
        new_status = "Partially Accepted"
    else:
        # No signer has responded yet
        new_status = quote_doc.status  # No change, still Sent

    # Update parent status only if changed
    if new_status != quote_doc.status:
        frappe.db.set_value("Service Quote", quote_doc.name, "status", new_status)

        quote_doc.add_comment(
            "Info",
            f"{contact_name} ({typed_name}) {response.lower()} the quote. "
            f"Quote status updated to: {new_status}",
        )

    # Notify assigned rep
    from ivm.client_portal.utils.notifications import notify_assigned_rep
    notify_assigned_rep(quote_doc.name, signer_row_name, response, reason=reason)
