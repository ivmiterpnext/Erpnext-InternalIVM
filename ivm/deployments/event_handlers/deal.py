"""
Event handlers for CRM Deal documents.
"""

import frappe
from frappe.model.document import Document

from ivm.deployments.services.provision_project_from_deal import create_projects_from_deal


def on_update(doc: Document, method: str | None = None) -> None:
    """When a CRM Deal status changes to Won, provision a Customer/iCorp client
    (for New Business) and create deployment Projects."""
    if doc.status != "Won" or not doc.has_value_changed("status"):
        return

    if not frappe.db.exists("Deployment Location", {"crm_deal": doc.name}):
        frappe.throw(
            "Cannot mark this deal as Won — no Deployment Locations are linked to it.",
            title="No Deployment Locations",
        )

    # Provision/resolve Customer before project creation so custom_customer is available.
    if doc.custom_deal_type == "New Business":
        from ivm.deployments.services.provision_client_from_deal import (
            provision_customer_and_icorp_client,
        )

        provision_customer_and_icorp_client(doc.name)
        doc.reload()  # pick up custom_customer set by provisioning

    elif doc.custom_deal_type == "Existing Business":
        from ivm.deployments.services.provision_client_from_deal import (
            link_existing_customer_to_deal,
        )

        link_existing_customer_to_deal(doc.name)
        doc.reload()  # pick up custom_customer resolved by lookup

    try:
        created = create_projects_from_deal(doc.name)

        if created:
            links = ", ".join(
                f'<a href="/app/project/{n}">{n}</a>' for n in created
            )
            frappe.msgprint(
                f"Created {len(created)} deployment(s): {links}",
                title="Deployments Created",
                indicator="green",
            )

    except Exception:
        frappe.log_error(
            title=f"Failed to create Deployments from CRM Deal {doc.name}",
            message=frappe.get_traceback(with_context=True),
        )
