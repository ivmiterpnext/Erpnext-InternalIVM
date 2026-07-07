"""
Remove the 'Link Project to Deal' Server Script.

This logic has been moved into the Project validate hook in
ivm.deployments.event_handlers.project._link_crm_deal.
"""

import frappe


def execute():
    if frappe.db.exists("Server Script", "Link Project to Deal"):
        frappe.delete_doc("Server Script", "Link Project to Deal", ignore_permissions=True)
        print("  Deleted Server Script 'Link Project to Deal'")
    else:
        print("  Server Script 'Link Project to Deal' not found — skipping")
