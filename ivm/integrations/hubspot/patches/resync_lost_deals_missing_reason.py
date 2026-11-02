"""
One-off backfill: re-sync CRM Deals stuck in a Lost-type status with no
lost_reason set.

Context: before the fix to deal_handler._apply_lost_reason (see
docs/agent/changelog.md), a HubSpot deal whose closed_lost_reason property
was empty would fail CRM Deal's own validate_lost_reason() every time it was
synced -- dealstage still mapped to a Lost-type CRM Deal Status via
_apply_status, but lost_reason was never populated, and CRM Deal mandates
lost_reason whenever its status-type is "Lost". This permanently failed the
sync for every deal HubSpot reps closed without recording a loss reason (51+
observed stuck this way on production as of 2026-11-02).

_apply_lost_reason now falls back to lost_reason="Other" with an explanatory
lost_notes when the mapped status is Lost-type and HubSpot gave no reason, so
once that fix is deployed, deals matching this patch's query will sync
successfully if re-triggered.

This patch finds every CRM Deal currently stuck in that state (status is a
Lost-type CRM Deal Status, lost_reason is empty, and a HubSpot deal ID is
present) and re-enqueues deal_handler.sync_deal for each, through the normal
enqueue_sync per-record dedup path.

Deliberately NOT registered in patches.txt -- this targets a known-broken
production state (ivmportal.frappe.cloud) that dev/test sites don't share,
and must only run after the _apply_lost_reason fix has been deployed. Run
manually, once (safe to re-run -- enqueue_sync dedups in-flight jobs, and
deals already fixed simply won't match the query on a second pass):

    bench --site ivmportal.frappe.cloud execute \\
        "ivm.integrations.hubspot.patches.resync_lost_deals_missing_reason.execute"
"""

from __future__ import annotations

import frappe

from ivm.integrations.hubspot.constants import DEAL_TYPE_ID, HUBSPOT_DEAL_ID_FIELD
from ivm.integrations.hubspot.sync_utils import enqueue_sync


def execute() -> None:
	lost_statuses = frappe.get_all("CRM Deal Status", filters={"type": "Lost"}, pluck="name")
	if not lost_statuses:
		print("No CRM Deal Status records of type 'Lost' found -- nothing to do.")
		return

	affected = frappe.get_all(
		"CRM Deal",
		filters=[
			["status", "in", lost_statuses],
			["lost_reason", "is", "not set"],
			[HUBSPOT_DEAL_ID_FIELD, "is", "set"],
		],
		fields=["name", HUBSPOT_DEAL_ID_FIELD],
	)

	if not affected:
		print("No affected deals found -- nothing to do.")
		return

	print(f"Found {len(affected)} deal(s) with a Lost status but no lost_reason -- re-enqueuing sync.")

	queued = skipped = 0
	for deal in affected:
		hubspot_deal_id = str(deal[HUBSPOT_DEAL_ID_FIELD])
		result = enqueue_sync(
			"ivm.integrations.hubspot.deal_handler.sync_deal",
			DEAL_TYPE_ID,
			hubspot_deal_id,
			hubspot_deal_id=hubspot_deal_id,
		)
		if result == "queued":
			queued += 1
		else:
			skipped += 1
		print(f"  {deal['name']} (hubspot_deal_id={hubspot_deal_id}): {result}")

	print(f"Done. Queued {queued}, skipped {skipped} (already in-flight).")
