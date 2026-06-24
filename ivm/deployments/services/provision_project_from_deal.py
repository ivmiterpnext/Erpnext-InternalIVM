"""
Provision one deployment Project per Deployment Location when a CRM Deal is won.

Data sources:
* CRM Deal            — deal-level fields (client, ownership, opportunity term, etc.)
* Deployment Location — site-level fields (location name, shipping address, devices, etc.)
"""

from typing import Any
import frappe
from frappe.utils import today, add_days
from ivm.deals.constants import SKIP_CHILD_FIELDS

_LOG = "deployments"

DEAL_TO_PROJECT_FIELDS: dict[str, str] = {
    "custom_machine_ownership_status": "machine_ownership_status",
    "custom_opportunity_term": "opportunity_term",
}

LOCATION_TO_PROJECT_FIELDS: dict[str, str] = {
    "equipment_type": "equipment_type",
    "wrap_type": "wrap_type",
    "card_reader_type": "card_reader_type",
    "connectivity_type": "connectivity_type",
    "locale": "locale",
    "ior": "ior",
    "expedited_delivery": "expedited_delivery",
    "install_type": "install_type",
    "shipping_address": "custom_shipping_address",
    "billing_address": "billing_address",
    "po_and_tracking": "po_and_tracking",
    "target_ship_date": "target_ship_date",
    "number_of_machines": "number_of_machines",
    "number_of_primary_lockers": "number_of_primary_lockers",
    "number_of_secondary_lockers": "number_of_secondary_lockers",
    "number_of_kiosks": "number_of_kiosks",
    "number_of_vaults": "number_of_vaults",
}

LOCATION_TO_PROJECT_CHILD_TABLES: dict[str, str] = {
    "smartstation_details": "custom_deployment_smartstation_details",
    "smartlocker_details": "custom_deployment_smartlocker_details",
    "smartsync_details": "custom_deployment_smartsync_details",
    "smartvault_details": "custom_deployment_smartvault_details",
    "smartcenter_details": "custom_deployment_smartcenter_details",
}


def _copy_flat_fields(doc: Any, mapping: dict[str, str]) -> dict[str, Any]:
    """Return {dest_field: value} for all non-empty mapped fields on doc."""
    return {
        dst: value
        for src, dst in mapping.items()
        if (value := doc.get(src)) is not None and value != ""
    }


def _copy_child_tables(
    doc: Any, mapping: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """Return {dest_table: [row_dicts]} for all non-empty mapped child tables on doc."""
    result: dict[str, list[dict[str, Any]]] = {}
    for src_table, dst_table in mapping.items():
        rows = doc.get(src_table) or []
        if not rows:
            continue
        copied = [
            {k: v for k, v in row.as_dict().items()
             if k not in SKIP_CHILD_FIELDS and v is not None and v != ""}
            for row in rows
        ]
        copied = [r for r in copied if r]
        if copied:
            result[dst_table] = copied
    return result


def create_projects_from_deal(crm_deal_name: str) -> list[str]:
    """Create one Project per Deployment Location linked to the given CRM Deal.
    Returns a list of created Project names."""
    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    locations = frappe.get_all(
        "Deployment Location",
        filters={"crm_deal": crm_deal_name},
        pluck="name",
    )

    if not locations:
        frappe.logger(_LOG).warning(
            f"CRM Deal {crm_deal_name} has no Deployment Locations — no Deployments created"
        )
        return []

    # Build deal-level field values once; shared across all Projects.
    deal_fields = _copy_flat_fields(deal, DEAL_TO_PROJECT_FIELDS)

    customer_name = deal.get("custom_client_id")
    if customer_name:
        deal_fields["customer"] = customer_name
        icorp_client_id = frappe.db.get_value("Customer", customer_name, "icorp_client_id")
        if icorp_client_id:
            deal_fields["client_id"] = icorp_client_id

    contacts = deal.get("contacts") or []
    primary_contact = next((r for r in contacts if r.is_primary), contacts[0] if contacts else None)
    if primary_contact:
        deal_fields["contact_name"] = primary_contact.contact

    created: list[str] = []

    for location_name in locations:
        project_name = _create_project_for_location(
            deal=deal,
            deal_fields=deal_fields,
            location_name=location_name,
        )
        if project_name:
            created.append(project_name)

    return created


def _create_project_for_location(
    deal: Any,
    deal_fields: dict[str, Any],
    location_name: str,
) -> str | None:
    """Create a single Project from one Deployment Location.
    Returns the new Project name, or None if a Project already exists for this location."""
    location = frappe.get_doc("Deployment Location", location_name)

    if frappe.db.exists("Project", {"custom_hubspot_deployment_site_id": location.hubspot_site_id or ""}):
        frappe.logger(_LOG).info(
            f"Deployment already exists for Deployment Location {location_name}, skipping"
        )
        return None

    location_fields = _copy_flat_fields(location, LOCATION_TO_PROJECT_FIELDS)
    child_rows = _copy_child_tables(location, LOCATION_TO_PROJECT_CHILD_TABLES)

    site_name = location.location_name or location_name
    start_date = location.target_ship_date or today()

    project = frappe.new_doc("Project")
    project.update({
        "project_name": f"{site_name} - {deal.name}",
        "project_type": "Deployment",
        "stage": "Waiting Assignment",
        "expected_start_date": start_date,
        "expected_end_date": add_days(start_date, 56),
        "custom_hubspot_deal_id": deal.get("custom_hubspot_deal_id") or "",
        "custom_hubspot_deployment_site_id": location.hubspot_site_id or "",
        **deal_fields,
        **location_fields,
        **child_rows,
    })

    # System-initiated creation; permissions enforced at the CRM Deal level.
    project.insert(ignore_permissions=True, ignore_mandatory=True)

    frappe.logger(_LOG).info(
        f"Created Deployment {project.name} from CRM Deal {deal.name} / "
        f"Deployment Location {location_name}"
    )

    return project.name
