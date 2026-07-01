"""
Clear all saved Desktop Layout records so every user gets a fresh icon grid
on next login. Required after removing the on_session_creation hook that was
overwriting workspace visibility state, which left stale layouts that excluded
the Frappe CRM icon.
"""

import frappe


def execute():
    frappe.db.sql("UPDATE `tabDesktop Layout` SET layout = '[]'")
    print("  Cleared all Desktop Layout records")
