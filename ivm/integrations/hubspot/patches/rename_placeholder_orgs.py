"""One-time script: rename HS-{id} placeholder CRM Organizations to their real HubSpot company name.

NOT registered in patches.txt — manual, one-time data-fix operation.

Run manually, dry-run first (default):
    bench --site <site> execute \
        "ivm.integrations.hubspot.patches.rename_placeholder_orgs.execute" \
        --kwargs '{"dry_run": true}'

Review the output, then apply:
    bench --site <site> execute \
        "ivm.integrations.hubspot.patches.rename_placeholder_orgs.execute" \
        --kwargs '{"dry_run": false}'

Idempotent — re-running after a clean pass finds zero remaining HS-* orgs.
"""

import time
import frappe


def execute(dry_run: bool = True) -> None:
    from ivm.integrations.hubspot import api
    from ivm.integrations.hubspot.api import HubSpotRateLimitExhausted

    placeholder_orgs = frappe.get_all(
        "CRM Organization",
        filters=[["name", "like", "HS-%"]],
        fields=["name", "custom_hubspot_company_id"],
    )

    total = len(placeholder_orgs)
    renamed = 0
    skipped_conflict = 0
    skipped_no_name = 0
    skipped_no_hs_id = 0
    errored = 0

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"[{mode}] Found {total} placeholder CRM Organizations (HS-*)")

    for i, org in enumerate(placeholder_orgs, 1):
        old_name = org["name"]
        hs_id = org.get("custom_hubspot_company_id")

        if not hs_id:
            print(f"  [{i}/{total}] {old_name}: no HubSpot ID — skipping")
            skipped_no_hs_id += 1
            continue

        try:
            result = _fetch_and_rename(old_name, hs_id, api, HubSpotRateLimitExhausted, dry_run)
            if result is None:
                skipped_no_name += 1
                print(f"  [{i}/{total}] {old_name}: HubSpot name is empty — skipping")
            elif result == "CONFLICT":
                skipped_conflict += 1
            else:
                renamed += 1
                verb = "would rename" if dry_run else "renamed"
                print(f"  [{i}/{total}] {old_name} → {result} ({verb})")
        except Exception as e:
            errored += 1
            print(f"  [{i}/{total}] {old_name}: ERROR — {e}")

    print(
        f"\n[{mode}] Done. Renamed: {renamed}, Conflict: {skipped_conflict}, "
        f"No name: {skipped_no_name}, No HS ID: {skipped_no_hs_id}, Errors: {errored}"
    )
    if dry_run:
        print("  DRY RUN — no documents were renamed. Re-run with dry_run=false to execute.")


def _fetch_and_rename(old_name, hs_id, api, RateLimitExc, dry_run, retried=False):
    """Fetch HubSpot name and rename (or preview). Returns new_name, None (no name), or 'CONFLICT'."""
    try:
        data = api.get_company(hs_id, properties=["name"])
    except RateLimitExc:
        if retried:
            raise
        print(f"    Rate limited on {old_name}, sleeping 10s...")
        time.sleep(10)
        return _fetch_and_rename(old_name, hs_id, api, RateLimitExc, dry_run, retried=True)

    props = data.get("properties", {})
    new_name = (props.get("name") or "").strip()

    if not new_name:
        return None

    if frappe.db.exists("CRM Organization", new_name):
        print(f"    {old_name}: '{new_name}' already exists — skipping")
        return "CONFLICT"

    if dry_run:
        return new_name

    frappe.rename_doc("CRM Organization", old_name, new_name, force=True)
    frappe.db.commit()
    return new_name
