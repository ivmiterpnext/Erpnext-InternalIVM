"""HubSpot Company → CRM Organization sync handler.

Webhook events are routed here via ``frappe.enqueue``, and each entry point
fetches the current HubSpot state and applies it to the corresponding Frappe
document.  Address fields are synced to a linked Address doc rather than flat
fields on the CRM Organization.
"""

from typing import Any

import frappe
from frappe.utils import flt

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    COMPANY_ADDRESS_PROPERTIES,
    COMPANY_FIELD_MAP,
    HUBSPOT_COMPANY_ID_FIELD,
    HUBSPOT_INDUSTRY_LABELS,
)
from ivm.integrations.hubspot.sync_utils import (
    ConcurrentCreateConflict,
    apply_field_map,
    bucket_employee_count,
    lookup_or_create,
    save_doc,
    set_acting_user,
    upsert_address,
)


def _apply_employee_count(doc: Any, raw_value: Any) -> None:
    """Bucket a raw employee count into Frappe's select range options."""
    bucketed = bucket_employee_count(str(raw_value) if raw_value else "")
    if bucketed:
        doc.no_of_employees = bucketed


def _apply_annual_revenue(doc: Any, raw_value: Any) -> None:
    """Coerce annual revenue to a numeric value."""
    if raw_value is not None and raw_value != "":
        doc.annual_revenue = flt(raw_value)


def _apply_industry(doc: Any, raw_value: Any) -> None:
    """Map a HubSpot industry enum key to an existing CRM Industry record.

    HubSpot sends enum keys like ``FACILITIES_SERVICES``. Only keys that have
    a corresponding CRM Industry record are mapped; unrecognised keys are
    silently skipped.
    """
    if not raw_value:
        return

    label = HUBSPOT_INDUSTRY_LABELS.get(raw_value)
    if not label:
        frappe.logger("hubspot").debug(
            f"No CRM Industry mapping for HubSpot industry key '{raw_value}' — skipping"
        )
        return

    doc.industry = label


COMPANY_TRANSFORMS: dict[str, Any] = {
    "no_of_employees": _apply_employee_count,
    "annual_revenue": _apply_annual_revenue,
    "industry": _apply_industry,
}


def handle_company_created(
    hubspot_company_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Create a CRM Organization from a newly created HubSpot company and sync fields."""
    set_acting_user(hubspot_user_id)
    try:
        doc, is_new = lookup_or_create(
            doctype="CRM Organization",
            hubspot_id_field=HUBSPOT_COMPANY_ID_FIELD,
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
    except ConcurrentCreateConflict:
        frappe.logger("hubspot").warning(
            f"HubSpot: concurrent create conflict for company {hubspot_company_id} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.company_handler.handle_company_created",
            queue="long",
            hubspot_company_id=hubspot_company_id,
            hubspot_user_id=hubspot_user_id,
        )
    except api.HubSpotRateLimitExhausted:
        frappe.logger("hubspot").warning(
            f"HubSpot: rate limit exhausted creating CRM Organization for company {hubspot_company_id} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.company_handler.handle_company_created",
            queue="long",
            hubspot_company_id=hubspot_company_id,
            hubspot_user_id=hubspot_user_id,
        )
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to create CRM Organization for company {hubspot_company_id}",
            message=frappe.get_traceback(with_context=True),
        )


def handle_company_updated(
    hubspot_company_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Sync a HubSpot company's current state to the matching CRM Organization."""
    set_acting_user(hubspot_user_id)
    try:
        org_name = frappe.db.get_value(
            "CRM Organization",
            {HUBSPOT_COMPANY_ID_FIELD: str(hubspot_company_id)},
            "name",
        )
        if not org_name:
            frappe.logger("hubspot").info(
                f"No CRM Organization found for HubSpot company {hubspot_company_id} "
                f"— provisioning before applying update"
            )
            handle_company_created(hubspot_company_id, hubspot_user_id)
            return
        _sync_company(hubspot_company_id, org_name)
    except api.HubSpotRateLimitExhausted:
        frappe.logger("hubspot").warning(
            f"HubSpot: rate limit exhausted syncing CRM Organization for company {hubspot_company_id} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.company_handler.handle_company_updated",
            queue="long",
            hubspot_company_id=hubspot_company_id,
            hubspot_user_id=hubspot_user_id,
        )
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync company {hubspot_company_id}",
            message=frappe.get_traceback(with_context=True),
        )


def _sync_company(hubspot_company_id: int | str, org_name: str) -> None:
    """Fetch company properties from HubSpot and apply to CRM Organization."""
    all_properties = ["name"] + list(COMPANY_FIELD_MAP.keys()) + COMPANY_ADDRESS_PROPERTIES
    hubspot_data = api.get_company(
        hubspot_company_id, properties=all_properties,
    )
    properties: dict[str, Any] = hubspot_data.get("properties", {})

    # Handle organization_name rename if the doc still has the placeholder name
    org_name = _maybe_rename_org(org_name, properties)

    doc = frappe.get_doc("CRM Organization", org_name)
    apply_field_map(doc, properties, COMPANY_FIELD_MAP, COMPANY_TRANSFORMS)
    save_doc(doc, "company")

    # Sync address fields to a linked Address doc
    _sync_org_address(org_name, properties)


def _maybe_rename_org(org_name: str, properties: dict[str, Any]) -> str:
    """Rename the CRM Organization from the HS-{id} placeholder to the real name.

    Returns the (possibly new) ``org_name``.  If the org already has a
    real name or no name is provided in the properties, returns the
    original name unchanged.
    """
    new_name = (properties.get("name") or "").strip()
    if not new_name:
        return org_name

    if not org_name.startswith("HS-"):
        return org_name

    if frappe.db.exists("CRM Organization", new_name):
        frappe.logger("hubspot").warning(
            f"CRM Organization '{new_name}' already exists — keeping placeholder name '{org_name}'"
        )
        return org_name

    try:
        frappe.rename_doc("CRM Organization", org_name, new_name, force=True)
        frappe.logger("hubspot").info(
            f"Renamed CRM Organization '{org_name}' → '{new_name}'"
        )
        return new_name
    except Exception:
        frappe.logger("hubspot").warning(
            f"HubSpot: failed to rename CRM Organization '{org_name}' → '{new_name}' — keeping placeholder"
        )
        return org_name


def _sync_org_address(org_name: str, properties: dict[str, Any]) -> None:
    """Create or update an Address doc linked to the CRM Organization."""
    upsert_address(
        address_line1=properties.get("address", ""),
        city=properties.get("city", ""),
        state=properties.get("state", ""),
        country=properties.get("country", ""),
        pincode=properties.get("zip", ""),
        link_doctype="CRM Organization",
        link_name=org_name,
    )
