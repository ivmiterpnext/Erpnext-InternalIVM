"""
Whitelisted API endpoints for triggering HubSpot backfill jobs from the desk.

Usage (browser console on any Frappe desk page):

    // Dry run — results appear in Error Log as "HubSpot Activity Backfill — Dry Run Results"
    frappe.call("ivm.integrations.hubspot.backfill_api.run_activity_backfill", {dry_run: 1}).then(r => console.log(r.message))

    // Real run — completion summary appears in Error Log as "HubSpot Activity Backfill — Completed"
    frappe.call("ivm.integrations.hubspot.backfill_api.run_activity_backfill", {dry_run: 0}).then(r => console.log(r.message))
"""

import frappe


@frappe.whitelist()
def run_activity_backfill(dry_run: bool = False) -> str:
    frappe.only_for("System Manager")
    frappe.enqueue(
        "ivm.integrations.hubspot.patches.backfill_activities_from_hubspot.execute",
        queue="long",
        timeout=3600,
        dry_run=frappe.utils.cint(dry_run),
    )
    mode = "dry run" if frappe.utils.cint(dry_run) else "live run"
    return f"Activity backfill ({mode}) enqueued. Check Error Log for results."
