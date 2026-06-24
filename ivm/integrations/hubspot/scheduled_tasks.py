"""
Scheduled HubSpot sync tasks.

Catches inbound reply emails that HubSpot does not surface via webhooks.
When a contact replies via a connected inbox, HubSpot creates an email
engagement silently — no ``object.creation`` webhook fires for it.  All other
engagement types (notes, calls, tasks, meetings) and all deal/contact/company
property changes are handled by webhooks, so this job only needs to cover
inbound emails.

Strategy
--------
Rather than polling each deal individually (N API calls), we use the CRM v4
batch associations endpoint to fetch all email IDs for all open deals in a
single call.  We then filter out emails already present in ``tabCommunication``
via a local DB check — zero additional API calls for emails already synced.
Only genuinely new emails trigger a property fetch and sync.

API cost per run
----------------
- ``ceil(open_deals / 100)`` batch association calls  (e.g. 1 call for ≤100 deals)
- 1 property fetch per new email found
- Total for a quiet hour with 200 open deals and no new replies: **2 API calls**
"""

import frappe

from ivm.integrations.hubspot import activity_handler
from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    EMAIL_PROPERTIES,
    ENGAGEMENT_TYPE_EMAILS,
    HUBSPOT_DEAL_ID_FIELD,
)

_LOG = "hubspot"

_CLOSED_STATUSES = frozenset({"Won", "Lost"})


def sync_inbound_emails() -> None:
    """Fetch and sync inbound reply emails for all open CRM Deals.

    Called hourly by the Frappe scheduler.
    """
    # --- 1. Load all open deals that have a HubSpot ID ---
    open_deals = frappe.get_all(
        "CRM Deal",
        filters=[
            [HUBSPOT_DEAL_ID_FIELD, "is", "set"],
            ["status", "not in", list(_CLOSED_STATUSES)],
        ],
        fields=["name", HUBSPOT_DEAL_ID_FIELD],
    )

    if not open_deals:
        return

    # Build lookup: hubspot_deal_id → crm_deal_name
    deal_map: dict[str, str] = {
        d[HUBSPOT_DEAL_ID_FIELD]: d["name"] for d in open_deals
    }
    hubspot_ids = list(deal_map.keys())

    frappe.logger(_LOG).info(
        f"HubSpot inbound email sync: checking {len(hubspot_ids)} open deal(s)"
    )

    # --- 2. Batch fetch all email IDs for all deals (1 API call per 100 deals) ---
    try:
        deal_email_ids = api.get_deal_email_ids_batch(hubspot_ids)
    except Exception:
        frappe.log_error(
            title="HubSpot: batch email association fetch failed",
            message=frappe.get_traceback(with_context=True),
        )
        return

    # --- 3. Collect all unique email IDs across all deals ---
    # Map email_id → list of crm_deal_names (an email can be associated to multiple deals)
    email_to_deals: dict[str, list[str]] = {}
    for hubspot_deal_id, email_ids in deal_email_ids.items():
        crm_deal_name = deal_map[hubspot_deal_id]
        for email_id in email_ids:
            email_to_deals.setdefault(email_id, []).append(crm_deal_name)

    if not email_to_deals:
        frappe.logger(_LOG).info("HubSpot inbound email sync: no emails found")
        return

    # --- 4. Filter to only emails not already synced (local DB check, no API call) ---
    all_email_ids = list(email_to_deals.keys())
    synced_message_ids = {
        row[0]
        for row in frappe.db.sql(
            """
            SELECT message_id FROM `tabCommunication`
            WHERE message_id IN %(message_ids)s
            """,
            {"message_ids": [f"<hubspot-email-{eid}>" for eid in all_email_ids]},
        )
    }

    new_email_ids = [
        eid for eid in all_email_ids
        if f"<hubspot-email-{eid}>" not in synced_message_ids
    ]

    frappe.logger(_LOG).info(
        f"HubSpot inbound email sync: {len(all_email_ids)} total emails, "
        f"{len(new_email_ids)} new"
    )

    if not new_email_ids:
        return

    # --- 5. Fetch and sync each new email (1 API call per new email) ---
    for email_id in new_email_ids:
        frappe.enqueue(
            "ivm.integrations.hubspot.scheduled_tasks._sync_one_email",
            queue="short",
            email_id=email_id,
            crm_deal_names=email_to_deals[email_id],
        )


def _sync_one_email(email_id: str, crm_deal_names: list[str]) -> None:
    """Fetch and sync a single new email engagement to its associated deals."""
    try:
        data = api.get_engagement(ENGAGEMENT_TYPE_EMAILS, email_id, EMAIL_PROPERTIES)
        props = data.get("properties", {})
        if "createdAt" not in props and data.get("createdAt"):
            props["_createdAt"] = data["createdAt"]

        for crm_deal_name in crm_deal_names:
            activity_handler._sync_email(email_id, props, crm_deal_name)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync inbound email {email_id}",
            message=frappe.get_traceback(with_context=True),
        )
