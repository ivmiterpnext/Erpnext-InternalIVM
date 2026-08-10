"""One-off reconciliation: re-check HubSpot for company associations on CRM
Deals that currently have no linked CRM Organization, and link them if found.

NOT registered in patches.txt — this is a manual, one-time data-fix operation,
not something that should silently re-run on every bench migrate. Run manually:
    bench --site <site> execute \
        "ivm.integrations.hubspot.patches.reconcile_missing_deal_orgs.execute"
"""

from __future__ import annotations

import frappe

from ivm.integrations.hubspot.constants import HUBSPOT_DEAL_ID_FIELD
from ivm.integrations.hubspot.deal_handler import _sync_organization


def execute() -> None:
    previous_user = frappe.session.user
    frappe.set_user("hubspot@ivm.local")
    try:
        deals = frappe.get_all(
            "CRM Deal",
            filters={
                "organization": ["in", ["", None]],
                HUBSPOT_DEAL_ID_FIELD: ["is", "set"],
            },
            fields=["name", HUBSPOT_DEAL_ID_FIELD],
        )
        deals = [d for d in deals if d.get(HUBSPOT_DEAL_ID_FIELD)]

        print(f"Found {len(deals)} deal(s) with no organization to re-check.")

        still_missing: list[str] = []
        for idx, d in enumerate(deals, start=1):
            hubspot_deal_id = d[HUBSPOT_DEAL_ID_FIELD]
            try:
                _sync_organization(hubspot_deal_id, d["name"])
            except Exception:
                frappe.log_error(
                    title=f"Reconcile: failed to sync organization for deal {d['name']}",
                    message=frappe.get_traceback(with_context=True),
                )

            if not frappe.db.get_value("CRM Deal", d["name"], "organization"):
                still_missing.append(d["name"])

            if idx % 25 == 0:
                print(f"  Processed {idx}/{len(deals)}...")

        frappe.db.commit()
        print(
            f"\nDone. Processed {len(deals)}. "
            f"Still missing organization: {len(still_missing)}"
        )
        print(still_missing)
    finally:
        frappe.set_user(previous_user)
