"""
Remove unused default CRM Deal Status records seeded by the CRM app.
"""

import frappe

# Most default statuses seeded by the CRM app's after_install hook are not used.
# These are replaced by HubSpot-aligned statuses via the CRM Deal Status fixture.
STATUSES_TO_REMOVE = [
    "Qualification",
    "Demo/Making",
    "Proposal/Quotation",
    "Negotiation",
    "Ready to Close",
]


def execute():
    # Only delete statuses that are not referenced by any deal.
    # Statuses still in use are left alone to avoid breaking existing records;
    # they will have to be cleaned up manually
    for status in STATUSES_TO_REMOVE:
        if not frappe.db.exists("CRM Deal Status", status):
            continue

        in_use = frappe.db.count("CRM Deal", filters={"status": status})
        if in_use:
            print(f"  Skipping '{status}' — still used by {in_use} deal(s)")
            continue

        frappe.delete_doc("CRM Deal Status", status, ignore_permissions=True)
        print(f"  Deleted CRM Deal Status '{status}'")

    frappe.db.commit()
