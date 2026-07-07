"""
Backfill CRM Deals, Contacts, and CRM Organizations from HubSpot.

Fetches all HubSpot deals with createdDate >= 2026-01-01 and syncs them
into Frappe CRM. For deals already Won in HubSpot:
  - Does NOT trigger the on_update win logic (Customer provisioning,
    Project creation). Status is written via frappe.db.set_value after insert.
  - Resolves custom_customer by matching HubSpot's client_id property to
    Customer.icorp_client_id. Written via frappe.db.set_value only.
  - If the matched Customer is missing icorp_client_id, looks it up from
    iCorp's Client endpoint (read-only, no POST) and backfills it.

Usage:
    bench --site dev.local execute \
        "ivm.integrations.hubspot.patches.backfill_deals_from_hubspot.execute"
"""

from __future__ import annotations

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    DEAL_FIELD_MAP,
    DEALSTAGE_TO_STATUS,
    HUBSPOT_DEAL_ID_FIELD,
)
from ivm.integrations.hubspot.deal_handler import (
    DEAL_TRANSFORMS,
    _sync_contacts,
    _sync_organization,
)
from ivm.integrations.hubspot.sync_utils import apply_field_map, lookup_or_create, save_doc

_SINCE_DATE = "2026-01-01"
_PROPERTIES = list(DEAL_FIELD_MAP.keys())


def execute() -> None:
    frappe.set_user("hubspot@ivm.local")

    print(f"Fetching HubSpot deals created since {_SINCE_DATE}...")
    hs_deals = _fetch_hubspot_deals(_SINCE_DATE)
    print(f"Found {len(hs_deals)} deal(s) to process.")

    icorp_client_map = _build_icorp_client_map()

    created = skipped = errors = 0

    for hs_deal in hs_deals:
        hs_id = str(hs_deal["id"])
        try:
            was_created = _sync_one_deal(hs_id, hs_deal["properties"], icorp_client_map)
            if was_created:
                created += 1
            else:
                skipped += 1
        except Exception:
            errors += 1
            frappe.log_error(
                title=f"Backfill: failed to sync HubSpot deal {hs_id}",
                message=frappe.get_traceback(with_context=True),
            )
            print(f"  ERROR: deal {hs_id} — see Error Log")

    frappe.db.commit()
    print(f"\nDone. Created: {created}, Skipped (already existed): {skipped}, Errors: {errors}")


def _fetch_hubspot_deals(since_date: str) -> list[dict]:
    """Page through HubSpot search results and return all matching deals."""
    filters = [
        {
            "propertyName": "createdate",
            "operator": "GTE",
            "value": f"{since_date}T00:00:00.000Z",
        }
    ]

    results = []
    after = None

    while True:
        response = api.search_deals(filters=filters, properties=_PROPERTIES, after=after)
        results.extend(response.get("results", []))

        next_page = response.get("paging", {}).get("next", {})
        after = next_page.get("after")
        if not after:
            break

    return results


def _sync_one_deal(hs_id: str, properties: dict, icorp_client_map: dict[str, str]) -> bool:
    """Sync a single HubSpot deal. Returns True if a new CRM Deal was created."""
    raw_stage = properties.get("dealstage") or ""
    real_status = DEALSTAGE_TO_STATUS.get(raw_stage, "Discovery")
    is_won = real_status == "Won"

    # Insert new deals with status="Discovery" so that on_update's
    # has_value_changed("status") check returns False when we later save
    # deal fields — preventing win logic from firing on new Won deals.
    doc, is_new = lookup_or_create(
        doctype="CRM Deal",
        hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
        hubspot_id=hs_id,
        defaults={"status": "Discovery"},
    )

    # Org must be linked before deal fields are saved (same order as live sync).
    _sync_organization(hs_id, doc.name)
    _sync_contacts(hs_id, doc.name)

    # Sync all deal fields except status — status is written via db.set_value below.
    _sync_deal_fields_no_win(doc.name, properties)

    # Write real status directly to DB — does not fire document events.
    current_db_status = frappe.db.get_value("CRM Deal", doc.name, "status")
    if current_db_status != real_status:
        frappe.db.set_value("CRM Deal", doc.name, "status", real_status)

    if is_won:
        _ensure_customer_linked(doc.name, properties, icorp_client_map)

    return is_new


def _sync_deal_fields_no_win(crm_deal_name: str, properties: dict) -> None:
    """Sync deal fields, excluding status.

    Status is excluded so that save_doc() cannot trigger on_update win logic
    via has_value_changed("status"). Status is written separately via db.set_value.
    """
    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    field_map_no_status = {k: v for k, v in DEAL_FIELD_MAP.items() if v != "status"}
    transforms_no_status = {k: v for k, v in DEAL_TRANSFORMS.items() if k != "status"}

    apply_field_map(deal, properties, field_map_no_status, transforms_no_status)
    save_doc(deal, "deal")


def _ensure_customer_linked(
    crm_deal_name: str,
    properties: dict,
    icorp_client_map: dict[str, str],
) -> None:
    """Resolve and write custom_customer for a Won deal via db.set_value only."""
    existing = frappe.db.get_value("CRM Deal", crm_deal_name, "custom_customer")
    if existing and frappe.db.exists("Customer", existing):
        return

    hs_client_id = str(properties.get("client_id") or "").strip()
    customer_name: str | None = None

    if hs_client_id:
        customer_name = frappe.db.get_value(
            "Customer", {"icorp_client_id": hs_client_id}, "name"
        )

        if not customer_name:
            icorp_client_name = icorp_client_map.get(hs_client_id)
            if icorp_client_name:
                customer_name = frappe.db.get_value(
                    "Customer", {"customer_name": icorp_client_name}, "name"
                )
                if customer_name:
                    frappe.db.set_value("Customer", customer_name, "icorp_client_id", hs_client_id)
                    print(f"  Backfilled icorp_client_id={hs_client_id} on Customer '{customer_name}'")

    if customer_name:
        frappe.db.set_value("CRM Deal", crm_deal_name, "custom_customer", customer_name)
        print(f"  Linked Customer '{customer_name}' to Won deal {crm_deal_name}")
    else:
        print(
            f"  WARNING: Won deal {crm_deal_name} — could not resolve Customer "
            f"(HubSpot client_id='{hs_client_id}'). Set custom_customer manually."
        )


def _build_icorp_client_map() -> dict[str, str]:
    """Fetch all iCorp clients once and return {icorp_id_str: client_name}.

    Used to resolve a HubSpot client_id to a Customer name when
    Customer.icorp_client_id has not yet been backfilled.
    Returns an empty dict if the iCorp API is unreachable.
    """
    from ivm.integrations.icorp import icorp_api_get

    try:
        data = icorp_api_get("Client?pageSize=9999&page=1")
    except Exception:
        frappe.log_error(
            title="Backfill: could not fetch iCorp clients",
            message=frappe.get_traceback(with_context=True),
        )
        print("  WARNING: iCorp Client API unreachable — icorp_client_id backfill skipped.")
        return {}

    items = data.get("data", [])
    return {
        str(item["id"]): str(item["name"]).strip()
        for item in items
        if item.get("id") and item.get("name")
    }
