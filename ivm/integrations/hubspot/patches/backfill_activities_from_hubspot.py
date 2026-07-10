"""
Backfill HubSpot engagement activities (notes, calls, emails, tasks, meetings)
for all CRM Deals that have a custom_hubspot_deal_id.

Registered in patches.txt (post_model_sync, end of file) — runs automatically
on migrate with dry_run=False. Can also be triggered manually via the
whitelisted API endpoint in backfill_api.py (supports dry_run), or via bench execute:

    bench --site <site> execute \
        "ivm.integrations.hubspot.patches.backfill_activities_from_hubspot.execute" \
        --kwargs '{"dry_run": true}'
"""

from __future__ import annotations

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.activity_handler import sync_deal_activities
from ivm.integrations.hubspot.constants import (
    ALL_ENGAGEMENT_TYPES,
    ENGAGEMENT_TYPE_CALLS,
    ENGAGEMENT_TYPE_EMAILS,
    ENGAGEMENT_TYPE_MEETINGS,
    ENGAGEMENT_TYPE_NOTES,
    ENGAGEMENT_TYPE_TASKS,
    HUBSPOT_DEAL_ID_FIELD,
    HUBSPOT_ENGAGEMENT_ID_FIELD,
)

_ENGAGEMENT_DOCTYPE_MAP = {
    ENGAGEMENT_TYPE_NOTES: "FCRM Note",
    ENGAGEMENT_TYPE_CALLS: "CRM Call Log",
    ENGAGEMENT_TYPE_TASKS: "CRM Task",
    ENGAGEMENT_TYPE_MEETINGS: "FCRM Note",
}


def execute(dry_run: bool = False) -> None:
    previous_user = frappe.session.user
    frappe.set_user("hubspot@ivm.local")
    try:
        deals = frappe.get_all(
            "CRM Deal",
            filters=[[HUBSPOT_DEAL_ID_FIELD, "is", "set"]],
            fields=["name", HUBSPOT_DEAL_ID_FIELD],
            order_by="creation asc",
        )

        if not deals:
            _log_result(dry_run, ["No CRM Deals with a HubSpot ID found — nothing to do."], 0, 0, 0)
            return

        mode = "DRY RUN" if dry_run else "LIVE"
        lines: list[str] = [f"[{mode}] Backfilling activities for {len(deals)} deal(s).\n"]

        total_new = total_existing = total_errors = 0

        for idx, deal in enumerate(deals, start=1):
            crm_deal_name = deal["name"]
            hubspot_deal_id = deal[HUBSPOT_DEAL_ID_FIELD]

            try:
                new, existing = _process_deal(hubspot_deal_id, crm_deal_name, dry_run)
            except api.HubSpotRateLimitExhausted as exc:
                lines.append(
                    f"[{idx}/{len(deals)}] {crm_deal_name} — rate limit hit "
                    f"(retry after {exc.retry_after_seconds}s). Stopping early."
                )
                lines.append("Re-run to resume. Already-synced records will be skipped.")
                _log_result(dry_run, lines, total_new, total_existing, total_errors)
                return
            except Exception:
                total_errors += 1
                frappe.log_error(
                    title=f"Activity backfill: failed on {crm_deal_name}",
                    message=frappe.get_traceback(with_context=True),
                )
                lines.append(f"[{idx}/{len(deals)}] {crm_deal_name} — ERROR (see Error Log)")
                continue

            total_new += new
            total_existing += existing

            label = "would create" if dry_run else "created"
            lines.append(
                f"[{idx}/{len(deals)}] {crm_deal_name} — "
                f"{new} {label}, {existing} already existed"
            )

            if not dry_run:
                frappe.db.commit()

        _log_result(dry_run, lines, total_new, total_existing, total_errors)
    finally:
        frappe.set_user(previous_user)


def _log_result(
    dry_run: bool,
    lines: list[str],
    total_new: int,
    total_existing: int,
    total_errors: int,
) -> None:
    label = "would create" if dry_run else "created"
    lines.append(
        f"\nDone. {label.capitalize()}: {total_new}, "
        f"Already existed: {total_existing}, Errors: {total_errors}"
    )
    mode = "Dry Run Results" if dry_run else "Completed"
    frappe.log_error(
        title=f"HubSpot Activity Backfill — {mode}",
        message="\n".join(lines),
    )


def _process_deal(
    hubspot_deal_id: str,
    crm_deal_name: str,
    dry_run: bool,
) -> tuple[int, int]:
    if dry_run:
        return _count_engagements(hubspot_deal_id, crm_deal_name)

    before = _count_existing(crm_deal_name)
    sync_deal_activities(hubspot_deal_id, crm_deal_name)
    after = _count_existing(crm_deal_name)

    return after - before, before


def _count_engagements(hubspot_deal_id: str, crm_deal_name: str) -> tuple[int, int]:
    total_remote = 0
    total_existing = 0

    for engagement_type in ALL_ENGAGEMENT_TYPES:
        ids = api.get_deal_engagement_ids(hubspot_deal_id, engagement_type)
        total_remote += len(ids)
        total_existing += _count_existing_engagements(engagement_type, ids, crm_deal_name)

    return total_remote - total_existing, total_existing


def _count_existing_engagements(
    engagement_type: str,
    engagement_ids: list[str],
    crm_deal_name: str,
) -> int:
    if not engagement_ids:
        return 0

    if engagement_type == ENGAGEMENT_TYPE_EMAILS:
        message_ids = [f"<hubspot-email-{eid}>" for eid in engagement_ids]
        rows = frappe.db.sql(
            "SELECT COUNT(*) FROM `tabCommunication` "
            "WHERE message_id IN %(ids)s AND reference_name = %(deal)s",
            {"ids": message_ids, "deal": crm_deal_name},
        )
        return rows[0][0] if rows else 0

    doctype = _ENGAGEMENT_DOCTYPE_MAP.get(engagement_type)
    if not doctype:
        return 0

    rows = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tab{doctype}` "
        f"WHERE `{HUBSPOT_ENGAGEMENT_ID_FIELD}` IN %(ids)s",
        {"ids": engagement_ids},
    )
    return rows[0][0] if rows else 0


def _count_existing(crm_deal_name: str) -> int:
    return sum([
        frappe.db.count("FCRM Note", {"reference_docname": crm_deal_name}),
        frappe.db.count("CRM Call Log", {"reference_doctype": "CRM Deal", "reference_docname": crm_deal_name}),
        frappe.db.count("CRM Task", {"reference_doctype": "CRM Deal", "reference_docname": crm_deal_name}),
        frappe.db.count("Communication", {"reference_doctype": "CRM Deal", "reference_name": crm_deal_name}),
    ])
