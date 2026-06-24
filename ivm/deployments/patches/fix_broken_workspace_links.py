"""
Clear broken workspace references that cause link validation errors on login.

1. Financial Reports workspace declared parent_page = "Accounting", but no
   Workspace record named "Accounting" exists.
2. Manufacturing workspace had a link to "BOM Stock Report" which no longer
   exists as a Report record.
3. Frappe CRM workspace was missing the required "type" field, causing a
   "Value missing for Workspace: Type" error on login.

All caused Frappe's link/mandatory validator to throw errors briefly on every
login during workspace sync.
"""

import frappe


def execute():
    if frappe.db.exists("Workspace", "Financial Reports"):
        frappe.db.set_value("Workspace", "Financial Reports", "parent_page", "", update_modified=False)
        print("  Cleared parent_page on Financial Reports workspace")

    frappe.db.delete("Workspace Link", {"parent": "Manufacturing", "link_to": "BOM Stock Report"})
    print("  Removed broken BOM Stock Report link from Manufacturing workspace")

    if frappe.db.exists("Workspace", "Frappe CRM"):
        frappe.db.set_value("Workspace", "Frappe CRM", "type", "Workspace", update_modified=False)
        print("  Set missing type on Frappe CRM workspace")
