"""
Whitelisted API for managing FCRM Notes on CRM Deals.

Notes are stored as standalone *FCRM Note* documents linked back 
to the deal via ``reference_doctype`` / ``reference_docname``.
"""

import frappe


@frappe.whitelist()
def get_notes(deal_name: str) -> list[dict]:
    """Return all FCRM Notes linked to a CRM Deal, newest first."""
    return frappe.get_list(
        "FCRM Note",
        filters={
            "reference_doctype": "CRM Deal",
            "reference_docname": deal_name,
        },
        fields=["name", "title", "content", "owner", "modified"],
        order_by="modified desc",
    )

@frappe.whitelist()
def add_note(deal_name: str, title: str, content: str) -> str:
    """Create a new FCRM Note linked to the given CRM Deal."""

    doc = frappe.get_doc(
        {
            "doctype": "FCRM Note",
            "title": title,
            "content": content,
            "reference_doctype": "CRM Deal",
            "reference_docname": deal_name,
        }
    )
    doc.insert()
    return doc.name

@frappe.whitelist()
def edit_note(note_name: str, title: str, content: str) -> None:
    """Update an existing FCRM Note."""

    doc = frappe.get_doc("FCRM Note", note_name)
    doc.title = title
    doc.content = content
    doc.save()

@frappe.whitelist()
def delete_note(note_name: str) -> None:
    """Delete an FCRM Note."""

    frappe.delete_doc("FCRM Note", note_name)
