"""Backfill icorp_client_id on Customer records from iCorp's client list.

Fetches all clients from iCorp (via the SV/Machine endpoint which returns
client_name alongside client_id), and for each one looks for a matching
Frappe Customer by name.  If found, writes the iCorp numeric client ID to
the Customer's icorp_client_id field.

Can be run as a bench patch or invoked directly via bench console:
    from ivm.integrations.icorp.patches.backfill_customer_icorp_client_id import execute
    execute()
"""

import frappe


def execute():
    from ivm.integrations.icorp import icorp_api_get

    # Pull all machines (which include client_id + client_name).
    # We only need the unique client mappings.
    try:
        data = icorp_api_get("SV/Machine?ActiveStatus=All&pageSize=99999&page=1")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "backfill_customer_icorp_client_id: API error")
        print("ERROR: Could not connect to iCorp API. See Error Log for details.")
        return

    items = data.get("data", [])
    if not items:
        print("No machines returned from iCorp — nothing to backfill.")
        return

    # Build a unique mapping of client_id → client_name from machine records.
    client_map: dict[str, str] = {}
    for item in items:
        cid = item.get("client_id") or item.get("id")
        cname = item.get("client_name") or item.get("name")
        if cid and cname:
            client_map[str(cid)] = str(cname).strip()

    updated = 0
    skipped = 0
    not_found = []

    for icorp_id, client_name in client_map.items():
        # Check if this Customer already has the icorp_client_id set.
        existing = frappe.db.get_value(
            "Customer", {"icorp_client_id": icorp_id}, "name"
        )
        if existing:
            skipped += 1
            continue

        # Try to find a matching Customer by name.
        customer_name = frappe.db.get_value("Customer", client_name, "name")
        if not customer_name:
            not_found.append(f"{client_name} (iCorp ID: {icorp_id})")
            continue

        frappe.db.set_value("Customer", customer_name, "icorp_client_id", icorp_id)
        updated += 1

    frappe.db.commit()

    print(f"Backfill complete: {updated} updated, {skipped} already set.")
    if not_found:
        print(f"{len(not_found)} iCorp clients had no matching Customer:")
        for name in not_found:
            print(f"  - {name}")
