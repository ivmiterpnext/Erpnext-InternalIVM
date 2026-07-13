"""
Backfill Contacts from HubSpot (createdate >= 2026-01-01).

Fills in HubSpot contacts that are NOT already covered by the deal backfill
(ivm.integrations.hubspot.patches.backfill_deals_from_hubspot), e.g. contacts
associated with a company/org that has no deal in HubSpot.

Unlike the deal backfill, this patch is CREATE-ONLY: existing Contacts
(matched by custom_hubspot_contact_id, falling back to email) are skipped
and never updated on re-run.

Registered in patches.txt (post_model_sync, immediately after
backfill_deals_from_hubspot — must run after it so it only fills the gap
of contacts not already synced via the deal cascade). Can also be run
manually via:
    bench --site <site> execute \\
        "ivm.integrations.hubspot.patches.backfill_contacts_from_hubspot.execute"

If a HubSpot rate limit is hit mid-run, the run stops early and returns
normally (does not raise) — check Error Log and re-run manually to resume.
"""

from __future__ import annotations

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    CONTACT_ADDRESS_PROPERTIES,
    CONTACT_FIELD_MAP,
    HUBSPOT_CONTACT_ID_FIELD,
)
from ivm.integrations.hubspot.contact_handler import upsert_contact

_SINCE_DATE = "2026-01-01"
_PROPERTIES = list(CONTACT_FIELD_MAP.keys()) + CONTACT_ADDRESS_PROPERTIES


def execute() -> None:
    previous_user = frappe.session.user
    frappe.set_user("hubspot@ivm.local")
    try:
        print(f"Fetching HubSpot contacts created since {_SINCE_DATE}...")
        hs_contacts = _fetch_hubspot_contacts(_SINCE_DATE)
        print(f"Found {len(hs_contacts)} contact(s) to process.")

        created = skipped = errors = 0

        for idx, hs_contact in enumerate(hs_contacts, start=1):
            hs_id = str(hs_contact["id"])
            try:
                was_created = _sync_one_contact(hs_id, hs_contact["properties"])
                if was_created:
                    created += 1
                else:
                    skipped += 1
            except api.HubSpotRateLimitExhausted as exc:
                print(
                    f"  Rate limit hit at contact {idx}/{len(hs_contacts)} "
                    f"(retry after {exc.retry_after_seconds}s). Stopping early — re-run to resume."
                )
                frappe.log_error(
                    title="Backfill: HubSpot rate limit exhausted — stopped early",
                    message=(
                        f"Processed {idx - 1}/{len(hs_contacts)} contacts before rate limit. "
                        f"Created: {created}, Skipped: {skipped}, Errors: {errors}. "
                        f"Re-run the patch to resume."
                    ),
                )
                break
            except Exception:
                errors += 1
                frappe.log_error(
                    title=f"Backfill: failed to sync HubSpot contact {hs_id}",
                    message=frappe.get_traceback(with_context=True),
                )
                print(f"  ERROR: contact {hs_id} — see Error Log")

        frappe.db.commit()
        print(f"\\nDone. Created: {created}, Skipped (already existed): {skipped}, Errors: {errors}")
    finally:
        frappe.set_user(previous_user)


def _fetch_hubspot_contacts(since_date: str) -> list[dict]:
    """Page through HubSpot search results and return all matching contacts."""
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
        try:
            response = api.search_contacts(filters=filters, properties=_PROPERTIES, after=after)
        except api.HubSpotRateLimitExhausted as exc:
            print(
                f"  Rate limit hit while fetching contact list "
                f"(retry after {exc.retry_after_seconds}s). "
                f"Returning {len(results)} contact(s) fetched so far — re-run to resume."
            )
            frappe.log_error(
                title="Backfill: HubSpot rate limit exhausted during contact fetch",
                message=f"Fetched {len(results)} contact(s) before rate limit. Re-run the patch to resume.",
            )
            break

        results.extend(response.get("results", []))
        next_page = response.get("paging", {}).get("next", {})
        after = next_page.get("after")
        if not after:
            break

    return results


def _sync_one_contact(hs_id: str, raw_properties: dict) -> bool:
    """Create a Frappe Contact if one doesn't already exist. Returns True if created."""
    if frappe.db.exists("Contact", {HUBSPOT_CONTACT_ID_FIELD: hs_id}):
        return False

    mapped = {
        frappe_key: raw_properties.get(hs_key) or ""
        for hs_key, frappe_key in CONTACT_FIELD_MAP.items()
    }
    email = (mapped.get("email") or "").strip()
    if email and frappe.db.exists("Contact", {"email_id": email}):
        return False

    address_props = {key: raw_properties.get(key) or "" for key in CONTACT_ADDRESS_PROPERTIES}

    contact_name = upsert_contact(mapped, hubspot_contact_id=hs_id, address_props=address_props)
    return bool(contact_name)
