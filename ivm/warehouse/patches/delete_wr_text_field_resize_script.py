"""
Delete the "Text Feild Resize" Client Script on Warehouse Request.

This script forced fixed pixel heights on ~46 textarea fields via raw jQuery
selectors on every form refresh. Every targeted field is either permanently
hidden (gated behind `depends_on: eval:doc.schema_version == 1`, and 100% of
existing Warehouse Request records are schema_version 2 — zero records at
version 1) or has since been converted to a "Data" fieldtype (serial_number,
prose_number, lan_mac_address), which renders as an <input>, not a <textarea>,
making the jQuery selector permanently a no-op regardless of visibility.

Removed from the client_script fixture; this patch deletes the leftover DB
record (fixture sync never deletes records absent from the JSON, so this
must be explicit).

Safe to run repeatedly (idempotent).
"""

import frappe


def execute():
    script_name = "Text Feild Resize"
    if frappe.db.exists("Client Script", script_name):
        frappe.delete_doc("Client Script", script_name, ignore_permissions=True, force=True)
        print(f"  Deleted Client Script: {script_name}")
    else:
        print(f"  Client Script {script_name} does not exist — skipping")

    frappe.clear_cache(doctype="Warehouse Request")
