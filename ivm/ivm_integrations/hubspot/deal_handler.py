"""
Sync HubSpot deals to CRM Deal records, including contacts and deployment sites.
"""

from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client
from ivm.ivm_integrations.hubspot.constants import (
    CONTACT_FIELD_MAP,
    DEAL_FIELD_MAP,
    DEALSTAGE_TO_STATUS,
    HUBSPOT_DEAL_TYPE_LABELS,
    MACHINE_TYPE_TO_CHILD_TABLE,
    PIPELINE_MAP,
)
from ivm.ivm_integrations.hubspot.sync_utils import (
    apply_field_map,
    coerce_value,
    lookup_or_create,
    save_doc,
    set_acting_user,
)


# ---------------------------------------------------------------------------
# Deal-specific value transforms
# ---------------------------------------------------------------------------


def _apply_deal_value(doc: Any, value: Any) -> None:
    doc.deal_value = frappe.utils.flt(value)


def _apply_status(doc: Any, value: Any) -> None:
    mapped = DEALSTAGE_TO_STATUS.get(value or "")
    if mapped:
        doc.status = mapped


def _apply_pipeline(doc: Any, value: Any) -> None:
    mapped = PIPELINE_MAP.get(value or "")
    if mapped:
        if frappe.db.exists("CRM Pipeline", mapped):
            doc.custom_pipeline = mapped
        else:
            frappe.logger("hubspot").warning(
                f"CRM Pipeline '{mapped}' (from HubSpot pipeline '{value}') "
                f"not found — skipping custom_pipeline"
            )
    elif value:
        frappe.logger("hubspot").warning(
            f"Unknown HubSpot pipeline ID '{value}' — skipping custom_pipeline"
        )


def _apply_deal_type(doc: Any, value: Any) -> None:
    if not value:
        return
    label = HUBSPOT_DEAL_TYPE_LABELS.get(value)
    if label:
        doc.custom_deal_type = label
    else:
        frappe.logger("hubspot").warning(
            f"Unknown HubSpot dealtype '{value}' — skipping custom_deal_type"
        )


def _apply_deal_owner(doc: Any, value: Any) -> None:
    if not value:
        return
    owner_email = hubspot_client.get_owner_email(value)
    if owner_email and frappe.db.exists("User", owner_email):
        doc.deal_owner = owner_email
    else:
        frappe.logger("hubspot").warning(
            f"HubSpot owner {value} resolved to '{owner_email}' "
            f"which is not a Frappe User — skipping deal_owner"
        )


DEAL_TRANSFORMS = {
    "deal_value": _apply_deal_value,
    "status": _apply_status,
    "custom_pipeline": _apply_pipeline,
    "custom_deal_type": _apply_deal_type,
    "deal_owner": _apply_deal_owner,
}


# ---------------------------------------------------------------------------
# Public entry points (called from webhook.py via frappe.enqueue)
# ---------------------------------------------------------------------------


def handle_deal_created(
    hubspot_deal_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Create a CRM Deal from a newly created HubSpot deal and sync all data."""
    set_acting_user(hubspot_user_id)
    try:
        doc, is_new = lookup_or_create(
            doctype="CRM Deal",
            hubspot_id_field="custom_hubspot_deal_id",
            hubspot_id=str(hubspot_deal_id),
            defaults={"status": "Discovery"},
        )
        if not is_new:
            frappe.log_error(
                title=f"HubSpot: CRM Deal already exists for deal {hubspot_deal_id}",
                message="Skipping duplicate deal creation.",
            )
            return
        _sync_deal(hubspot_deal_id, doc.name)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to create CRM Deal for deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )


def handle_deal_updated(
    hubspot_deal_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Sync a HubSpot deal's current state to the matching CRM Deal."""
    set_acting_user(hubspot_user_id)
    try:
        crm_deal_name = frappe.db.get_value(
            "CRM Deal", {"custom_hubspot_deal_id": str(hubspot_deal_id)}, "name",
        )
        if not crm_deal_name:
            frappe.logger("hubspot").warning(
                f"No CRM Deal found for HubSpot deal {hubspot_deal_id}, skipping update"
            )
            return
        _sync_deal(hubspot_deal_id, crm_deal_name)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )


# ---------------------------------------------------------------------------
# Internal sync orchestration
# ---------------------------------------------------------------------------


def _sync_deal(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Sync deal-level fields and contacts.

    Deployment locations, machines, bins, and activities are no longer
    synced here — they have their own generic webhook subscriptions and
    are handled independently by ``deployment_site_handler`` and
    ``activity_handler``.
    """
    hubspot_data = hubspot_client.get_deal(
        hubspot_deal_id, properties=list(DEAL_FIELD_MAP.keys())
    )
    properties: dict[str, Any] = hubspot_data.get("properties", {})

    _sync_deal_fields(crm_deal_name, properties)
    _sync_organization(hubspot_deal_id, crm_deal_name)
    _sync_contacts(hubspot_deal_id, crm_deal_name)


def _sync_deal_fields(crm_deal_name: str, properties: dict[str, Any]) -> None:
    """Update deal-level fields on the CRM Deal from HubSpot deal properties."""
    deal = frappe.get_doc("CRM Deal", crm_deal_name)
    apply_field_map(deal, properties, DEAL_FIELD_MAP, DEAL_TRANSFORMS)
    save_doc(deal, "deal")


# ---------------------------------------------------------------------------
# Organization sync
# ---------------------------------------------------------------------------


def _sync_organization(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Link the first associated HubSpot company to the CRM Deal's organization field."""
    try:
        company_ids = hubspot_client.get_deal_company_ids(hubspot_deal_id)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch company associations for deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not company_ids:
        return

    # Use the first associated company (deals typically have one)
    org_name = frappe.db.get_value(
        "CRM Organization",
        {"custom_hubspot_company_id": str(company_ids[0])},
        "name",
    )
    if not org_name:
        frappe.logger("hubspot").info(
            f"No CRM Organization found for HubSpot company {company_ids[0]} "
            f"— provisioning from HubSpot"
        )
        from ivm.ivm_integrations.hubspot.company_handler import handle_company_created
        handle_company_created(company_ids[0])
        org_name = frappe.db.get_value(
            "CRM Organization",
            {"custom_hubspot_company_id": str(company_ids[0])},
            "name",
        )
        if not org_name:
            frappe.logger("hubspot").warning(
                f"Failed to provision CRM Organization for HubSpot company {company_ids[0]} "
                f"— skipping organization link on deal {crm_deal_name}"
            )
            return

    deal = frappe.get_doc("CRM Deal", crm_deal_name)
    if deal.organization == org_name:
        return

    deal.organization = org_name
    save_doc(deal, "deal")
    frappe.logger("hubspot").info(
        f"Linked CRM Organization '{org_name}' to CRM Deal {crm_deal_name}"
    )


# ---------------------------------------------------------------------------
# Contact sync
# ---------------------------------------------------------------------------


def _sync_contacts(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Fetch contacts associated with the HubSpot deal and link them to the CRM Deal."""
    try:
        contact_ids = hubspot_client.get_deal_contact_ids(hubspot_deal_id)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch contact associations for deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not contact_ids:
        return

    hs_properties = list(CONTACT_FIELD_MAP.keys())
    contacts: list[dict[str, Any]] = []

    for contact_id in contact_ids:
        try:
            contact_data = hubspot_client.get_contact(contact_id, properties=hs_properties)
            props = contact_data.get("properties", {})
            contacts.append({
                frappe_key: props.get(hs_key) or ""
                for hs_key, frappe_key in CONTACT_FIELD_MAP.items()
            })
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to fetch contact {contact_id} for deal {hubspot_deal_id}",
                message=frappe.get_traceback(with_context=True),
            )

    if contacts:
        _ensure_contacts(crm_deal_name, contacts)


def _ensure_contacts(crm_deal_name: str, contacts: list[dict[str, Any]]) -> None:
    """Create Contact records (if needed) and link them to the CRM Deal."""
    from ivm.ivm_integrations.hubspot.contact_handler import upsert_contact

    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    for idx, entry in enumerate(contacts):
        contact_name = upsert_contact(entry)
        if not contact_name:
            continue

        if any(row.contact == contact_name for row in (deal.get("contacts") or [])):
            continue

        deal.append("contacts", {"contact": contact_name, "is_primary": 1 if idx == 0 else 0})

    deal.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Deployment location helpers (used by deployment_site_handler)
# ---------------------------------------------------------------------------
# These remain here to avoid circular imports — deployment_site_handler
# imports them for its webhook-driven upserts.


def _apply_site_properties(loc: Any, site_properties: dict[str, Any]) -> None:
    """Apply HubSpot site properties to a Deployment Location doc."""
    from ivm.ivm_integrations.hubspot.constants import SITE_FIELD_MAP

    meta = frappe.get_meta("Deployment Location")

    for hs_key, loc_field in SITE_FIELD_MAP.items():
        value = site_properties.get(hs_key)
        if value is None or value == "":
            continue

        df = meta.get_field(loc_field)
        loc.set(loc_field, coerce_value(value, df))


def _apply_machine_data(
    loc: Any,
    machines: dict[str, list[dict[str, Any]]],
) -> None:
    """Replace machine child tables on the Deployment Location with fresh data."""
    all_child_tables = set(MACHINE_TYPE_TO_CHILD_TABLE.values())

    for child_table in all_child_tables:
        loc.set(child_table, [])

    for child_table, rows in machines.items():
        for row in rows:
            if row:
                loc.append(child_table, row)
