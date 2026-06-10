"""
Event handlers for CRM Deal documents.
"""

import frappe
from frappe.model.document import Document

from ivm.deployments.services.provision_project_from_deal import create_projects_from_deal


def on_update(doc: Document, method: str | None = None) -> None:
    """When a CRM Deal status changes to Won, create one deployment Project per Deployment Location."""
    if doc.status != "Won":
        return

    if not doc.has_value_changed("status"):
        return

    try:
        created = create_projects_from_deal(doc.name)

        if created:
            links = ", ".join(
                f'<a href="/app/project/{n}">{n}</a>' for n in created
            )
            frappe.msgprint(
                f"Created {len(created)} deployment Project(s): {links}",
                title="Deployment Projects Created",
                indicator="green",
            )
        else:
            frappe.msgprint(
                "No Deployment Locations found on this deal — no Projects were created.",
                title="No Projects Created",
                indicator="orange",
            )

    except Exception:
        frappe.log_error(
            title=f"Failed to create Projects from CRM Deal {doc.name}",
            message=frappe.get_traceback(with_context=True),
        )
