"""One-time script: rename HS-{id} placeholder CRM Organizations to their real HubSpot company name.

Usage (production — inside Docker container):
    bench --site ivmportal.frappe.cloud execute \
        "exec(open('/home/frappe/frappe-bench/apps/ivm/ivm/integrations/hubspot/patches/rename_placeholder_orgs.py').read(), globals())"

Usage (dev):
    bench --site dev.local execute \
        "exec(open('/home/lhammond/frappe-bench/apps/ivm/ivm/integrations/hubspot/patches/rename_placeholder_orgs.py').read(), globals())"
"""

import time
import frappe


def main():
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

    print(f"Found {total} placeholder CRM Organizations (HS-*)")

    for i, org in enumerate(placeholder_orgs, 1):
        old_name = org["name"]
        hs_id = org.get("custom_hubspot_company_id")

        if not hs_id:
            print(f"  [{i}/{total}] {old_name}: no HubSpot ID — skipping")
            skipped_no_hs_id += 1
            continue

        try:
            result = _fetch_and_rename(old_name, hs_id, api, HubSpotRateLimitExhausted)
            if result is None:
                skipped_no_name += 1
                print(f"  [{i}/{total}] {old_name}: HubSpot name is empty — skipping")
            elif result == "CONFLICT":
                skipped_conflict += 1
            else:
                renamed += 1
                print(f"  [{i}/{total}] {old_name} → {result}")
        except Exception as e:
            errored += 1
            print(f"  [{i}/{total}] {old_name}: ERROR — {e}")

    print(
        f"\nDone. Renamed: {renamed}, Conflict: {skipped_conflict}, "
        f"No name: {skipped_no_name}, No HS ID: {skipped_no_hs_id}, Errors: {errored}"
    )


def _fetch_and_rename(old_name, hs_id, api, RateLimitExc, retried=False):
    """Fetch HubSpot name and rename. Returns new_name, None (no name), or 'CONFLICT'."""
    try:
        data = api.get_company(hs_id, properties=["name"])
    except RateLimitExc:
        if retried:
            raise
        print(f"    Rate limited on {old_name}, sleeping 10s...")
        time.sleep(10)
        return _fetch_and_rename(old_name, hs_id, api, RateLimitExc, retried=True)

    props = data.get("properties", {})
    new_name = (props.get("name") or "").strip()

    if not new_name:
        return None

    if frappe.db.exists("CRM Organization", new_name):
        print(f"    {old_name}: '{new_name}' already exists — skipping")
        return "CONFLICT"

    frappe.rename_doc("CRM Organization", old_name, new_name, force=True)
    frappe.db.commit()
    return new_name


main()
