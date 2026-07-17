"""
Sync HubSpot deals to CRM Deal records, including contacts and deployment sites.
"""

from typing import Any

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    CONTACT_FIELD_MAP,
    DEAL_FIELD_MAP,
    DEALSTAGE_TO_STATUS,
    HUBSPOT_COMPANY_ID_FIELD,
    HUBSPOT_DEAL_ID_FIELD,
    HUBSPOT_DEAL_TYPE_LABELS,
    PIPELINE_MAP,
)
from ivm.integrations.hubspot.sync_utils import (
    apply_field_map,
    lookup_or_create,
    save_doc,
    set_acting_user,
)


def _apply_deal_value(doc: Any, value: Any) -> None:
    doc.deal_value = frappe.utils.flt(value)


def _apply_status(doc: Any, value: Any) -> None:
    mapped = DEALSTAGE_TO_STATUS.get(value or "")
    if mapped:
        doc.status = mapped


def _apply_lost_reason(doc: Any, value: Any) -> None:
    """Map a HubSpot closed_lost_reason to a CRM Lost Reason record.

    Attempts case-insensitive matching against existing CRM Lost Reason
    records.  Falls back to "Other" with the raw value in ``lost_notes``
    if no match is found.  Only applies when the deal status is "Lost".
    """
    if not value:
        return

    value_str = str(value).strip()
    if not value_str:
        return

    # Build a case-insensitive lookup of existing lost reasons
    existing = frappe.get_all("CRM Lost Reason", pluck="name")
    lookup = {name.lower(): name for name in existing}

    matched = lookup.get(value_str.lower())
    if matched:
        doc.lost_reason = matched
    else:
        doc.lost_reason = "Other"
        doc.lost_notes = value_str
        frappe.logger("hubspot").info(
            f"HubSpot closed_lost_reason '{value_str}' did not match any "
            f"CRM Lost Reason — set to 'Other' with lost_notes"
        )


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
    owner_email = api.get_owner_email(value)
    if owner_email and frappe.db.exists("User", owner_email):
        doc.deal_owner = owner_email
    else:
        frappe.logger("hubspot").warning(
            f"HubSpot owner {value} resolved to '{owner_email}' "
            f"which is not a Frappe User — skipping deal_owner"
        )


def _apply_client_id(doc: Any, value: Any) -> None:
    """Resolve HubSpot's numeric iCorp client ID to a Frappe Customer name.

    HubSpot stores the iCorp numeric client ID in the ``client_id`` property
    (e.g. ``"1042"``).  ``custom_customer`` is a Link → Customer field, so
    we must look up the Customer whose ``icorp_client_id`` matches before
    writing the value, otherwise Frappe silently discards the raw numeric string.
    """
    if not value:
        return
    customer_name = frappe.db.get_value(
        "Customer", {"icorp_client_id": str(value)}, "name"
    )
    if customer_name:
        doc.custom_customer = customer_name
    else:
        frappe.logger("hubspot").warning(
            f"HubSpot client_id '{value}' did not match any Customer "
            f"(icorp_client_id) — skipping custom_customer"
        )


DEAL_TRANSFORMS = {
    "deal_value": _apply_deal_value,
    "status": _apply_status,
    "lost_reason": _apply_lost_reason,
    "custom_pipeline": _apply_pipeline,
    "custom_deal_type": _apply_deal_type,
    "deal_owner": _apply_deal_owner,
    "custom_customer": _apply_client_id,
}


def handle_deal_created(
    hubspot_deal_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Create a CRM Deal from a newly created HubSpot deal and sync all data."""
    set_acting_user(hubspot_user_id)
    try:
        doc, is_new = lookup_or_create(
            doctype="CRM Deal",
            hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
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
    except api.HubSpotRateLimitExhausted:
        frappe.logger("hubspot").warning(
            f"HubSpot: rate limit exhausted creating CRM Deal for deal {hubspot_deal_id} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.deal_handler.handle_deal_created",
            queue="long",
            hubspot_deal_id=hubspot_deal_id,
            hubspot_user_id=hubspot_user_id,
        )
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
            "CRM Deal", {HUBSPOT_DEAL_ID_FIELD: str(hubspot_deal_id)}, "name",
        )
        if not crm_deal_name:
            frappe.logger("hubspot").warning(
                f"No CRM Deal found for HubSpot deal {hubspot_deal_id}, skipping update"
            )
            return
        _sync_deal(hubspot_deal_id, crm_deal_name)
    except api.HubSpotRateLimitExhausted:
        frappe.logger("hubspot").warning(
            f"HubSpot: rate limit exhausted syncing CRM Deal for deal {hubspot_deal_id} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.deal_handler.handle_deal_updated",
            queue="long",
            hubspot_deal_id=hubspot_deal_id,
            hubspot_user_id=hubspot_user_id,
        )
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )


def _sync_deal(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Sync deal-level fields and contacts.

    Deployment locations, machines, bins, and activities are no longer
    synced here — they have their own generic webhook subscriptions and
    are handled independently by ``deployment_site_handler`` and
    ``activity_handler``.

    Organization is synced before deal fields so that when _sync_deal_fields
    saves the deal (triggering on_update), the organization link is already
    in place — ensuring customer provisioning can find it if the deal is Won.
    """
    hubspot_data = api.get_deal(
        hubspot_deal_id, properties=list(DEAL_FIELD_MAP.keys())
    )
    properties: dict[str, Any] = hubspot_data.get("properties", {})

    _sync_organization(hubspot_deal_id, crm_deal_name)
    _sync_contacts(hubspot_deal_id, crm_deal_name)
    _sync_deal_fields(crm_deal_name, properties)


def _sync_deal_fields(crm_deal_name: str, properties: dict[str, Any]) -> None:
    """Update deal-level fields on the CRM Deal from HubSpot deal properties."""
    deal = frappe.get_doc("CRM Deal", crm_deal_name)
    apply_field_map(deal, properties, DEAL_FIELD_MAP, DEAL_TRANSFORMS)
    save_doc(deal, "deal")


def _sync_organization(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Link the first associated HubSpot company to the CRM Deal's organization field."""
    try:
        company_ids = api.get_deal_company_ids(hubspot_deal_id)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch company associations for deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not company_ids:
        return

    org_name = frappe.db.get_value(
        "CRM Organization",
        {HUBSPOT_COMPANY_ID_FIELD: str(company_ids[0])},
        "name",
    )
    if not org_name:
        frappe.logger("hubspot").info(
            f"No CRM Organization found for HubSpot company {company_ids[0]} "
            f"— provisioning from HubSpot"
        )
        from ivm.integrations.hubspot.company_handler import handle_company_created
        handle_company_created(company_ids[0])
        org_name = frappe.db.get_value(
            "CRM Organization",
            {HUBSPOT_COMPANY_ID_FIELD: str(company_ids[0])},
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


def _sync_contacts(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Fetch contacts associated with the HubSpot deal and link them to the CRM Deal."""
    try:
        contact_ids = api.get_deal_contact_ids(hubspot_deal_id)
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
            contact_data = api.get_contact(contact_id, properties=hs_properties)
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
    from ivm.integrations.hubspot.contact_handler import upsert_contact

    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    for idx, entry in enumerate(contacts):
        contact_name = upsert_contact(entry)
        if not contact_name:
            continue

        if any(row.contact == contact_name for row in (deal.get("contacts") or [])):
            continue

        deal.append("contacts", {"contact": contact_name, "is_primary": 1 if idx == 0 else 0})

    deal.save(ignore_permissions=True)
