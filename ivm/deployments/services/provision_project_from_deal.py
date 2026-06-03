"""
Provision a deployment Project from a won CRM Deal.
"""

from typing import Any
import frappe
from frappe.utils import today, add_days
from ivm.deals.constants import SKIP_CHILD_FIELDS

DEAL_TO_PROJECT_FIELDS: dict[str, str] = {
    "custom_location_name": "site_location_name",
    "custom_equipment_type": "equipment_type",
    "custom_machine_ownership_status": "machine_ownership_status",
    "custom_wrap_type": "wrap_type",
    "custom_card_reader_type": "card_reader_type",
    "custom_connectivity_type": "connectivity_type",
    "custom_locale": "locale",
    "custom_expedited_delivery": "expedited_delivery",
    "custom_install_type": "install_type",
    "custom_client_id": "client_id",
    "custom_master_client_id": "master_client_id",
    "custom_sales_rep": "sales_rep",
    "custom_ior": "ior",
    "custom_opportunity_term": "opportunity_term",
    "custom_shipping_address": "custom_shipping_address",
    "custom_billing_address": "billing_address",
    "custom_po_and_tracking": "po_and_tracking",
    "custom_target_ship_date": "target_ship_date",
}

DEAL_TO_PROJECT_CHILD_TABLES: dict[str, str] = {
    "custom_deal_smartstation_details": "custom_deployment_smartstation_details",
    "custom_deal_smartlocker_details": "custom_deployment_smartlocker_details",
    "custom_deal_smartsync_details": "custom_deployment_smartsync_details",
    "custom_deal_smartvault_details": "custom_deployment_smartvault_details",
    "custom_deal_smartcenter_details": "custom_deployment_smartcenter_details",
}


def create_project_from_deal(crm_deal_name: str) -> str:
    """
    Reads flat fields and child table rows from the CRM Deal and creates
    a Project with matching data.
    """

    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    project_fields: dict[str, Any] = {}
    for deal_field, project_field in DEAL_TO_PROJECT_FIELDS.items():
        value = deal.get(deal_field)
        if value is not None and value != "":
            project_fields[project_field] = value

    child_rows: dict[str, list[dict[str, Any]]] = {}
    for deal_table, project_table in DEAL_TO_PROJECT_CHILD_TABLES.items():
        deal_rows = deal.get(deal_table) or []
        if not deal_rows:
            continue

        rows: list[dict[str, Any]] = []
        for deal_row in deal_rows:
            row = {
                k: v for k, v in deal_row.as_dict().items()
                if k not in SKIP_CHILD_FIELDS and v is not None and v != ""
            }
            if row:
                rows.append(row)

        if rows:
            child_rows[project_table] = rows

    site_name = deal.get("custom_location_name") or crm_deal_name
    project_name = f"{site_name} - {crm_deal_name}"

    start_date = today()

    project = frappe.new_doc("Project")
    project.update({
        "project_name": project_name,
        "project_type": "Deployment",
        "stage": "Waiting Assignment",
        "expected_start_date": start_date,
        "expected_end_date": add_days(start_date, 56),
        "custom_hubspot_deal_id": deal.get("custom_hubspot_deal_id") or "",
        **project_fields,
        **child_rows,
    })

    # System-initiated creation on behalf of the user; permissions are
    # enforced at the CRM Deal level before this function is called.
    project.insert(ignore_permissions=True, ignore_mandatory=True)

    frappe.logger("deployments").info(
        f"Created Project {project.name} from CRM Deal {crm_deal_name}"
    )

    return project.name
