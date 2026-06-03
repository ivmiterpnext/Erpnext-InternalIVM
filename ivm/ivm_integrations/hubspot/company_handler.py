"""
HubSpot Company to CRM Organization sync handler.

webhook events are routed here via ``frappe.enqueue``, and each entry point 
fetches the current HubSpot state and applies it to the corresponding Frappe document.
"""

from typing import Any
import frappe
from ivm.ivm_integrations.hubspot import hubspot_client
from ivm.ivm_integrations.hubspot.constants import COMPANY_FIELD_MAP
from ivm.ivm_integrations.hubspot.sync_utils import (
    apply_field_map,
    lookup_or_create,
    save_doc,
    set_hubspot_user,
)

# TODO: HubSpot ID field on CRM Organization.  Must be added as a Custom Field
# (custom_hubspot_company_id) on the CRM Organization DocType before handler will work.
HUBSPOT_ID_FIELD = "custom_hubspot_company_id"

# TODO: Add entries here as field mapping is finalized.  Each transform receives
# (doc, raw_hubspot_value) and mutates the doc directly.
COMPANY_TRANSFORMS: dict[str, Any] = {
    # Example (uncomment when employee-count bucketing is decided):
    # "no_of_employees": _apply_employee_count,
}


def handle_company_created(hubspot_company_id: int | str) -> None:
    """Create a CRM Organization from a newly created HubSpot company and sync fields."""
    set_hubspot_user()
    try:
        doc, is_new = lookup_or_create(
            doctype="CRM Organization",
            hubspot_id_field=HUBSPOT_ID_FIELD,
            hubspot_id=str(hubspot_company_id),
            defaults={"organization_name": f"HS-{hubspot_company_id}"},
        )
        if not is_new:
            frappe.log_error(
                title=f"HubSpot: CRM Organization already exists for company {hubspot_company_id}",
                message="Skipping duplicate company creation.",
            )
            return
        _sync_company(hubspot_company_id, doc.name)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to create CRM Organization for company {hubspot_company_id}",
            message=frappe.get_traceback(with_context=True),
        )


def handle_company_updated(hubspot_company_id: int | str) -> None:
    """Sync a HubSpot company's current state to the matching CRM Organization."""
    set_hubspot_user()
    try:
        org_name = frappe.db.get_value(
            "CRM Organization",
            {HUBSPOT_ID_FIELD: str(hubspot_company_id)},
            "name",
        )
        if not org_name:
            frappe.logger("hubspot").warning(
                f"No CRM Organization found for HubSpot company {hubspot_company_id}, "
                f"skipping update"
            )
            return
        _sync_company(hubspot_company_id, org_name)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync company {hubspot_company_id}",
            message=frappe.get_traceback(with_context=True),
        )


# ---------------------------------------------------------------------------
# Internal sync
# ---------------------------------------------------------------------------


def _sync_company(hubspot_company_id: int | str, org_name: str) -> None:
    """Fetch company properties from HubSpot and apply to CRM Organization."""
    if not COMPANY_FIELD_MAP:
        frappe.logger("hubspot").info(
            f"COMPANY_FIELD_MAP is empty — skipping field sync for company {hubspot_company_id}"
        )
        return

    hubspot_data = hubspot_client.get_company(
        hubspot_company_id, properties=list(COMPANY_FIELD_MAP.keys())
    )
    properties: dict[str, Any] = hubspot_data.get("properties", {})

    doc = frappe.get_doc("CRM Organization", org_name)
    apply_field_map(doc, properties, COMPANY_FIELD_MAP, COMPANY_TRANSFORMS or None)
    save_doc(doc, "company")
