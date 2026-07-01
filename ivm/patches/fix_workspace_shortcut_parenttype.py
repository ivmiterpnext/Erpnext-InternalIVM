"""
Fix Workspace Shortcut records missing parenttype and parentfield.

All Workspace Shortcut records were inserted without parenttype or parentfield
set, causing Frappe's mandatory field validator to throw MandatoryError during
bench migrate and aborting all subsequent patches.

Two operations:
1. For shortcuts whose parent Workspace record exists: set parenttype =
   "Workspace" and parentfield = "shortcuts".
2. For shortcuts whose parent Workspace record does not exist (orphaned):
   delete them. The parent workspaces (IVM, Warehouse Management, Wiki, etc.)
   either do not exist in the DB or are being rebuilt via the Frappe UI.
"""

import frappe


def execute():
    # Fix shortcuts whose parent Workspace exists
    fixed = frappe.db.sql(
        """
        UPDATE `tabWorkspace Shortcut` ws
        INNER JOIN `tabWorkspace` w ON ws.parent = w.name
        SET ws.parenttype = 'Workspace', ws.parentfield = 'shortcuts'
        WHERE ws.parenttype IS NULL
        """,
    )
    fixed_count = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    print(f"  Fixed parenttype/parentfield on {fixed_count} Workspace Shortcut records")

    # Delete orphaned shortcuts whose parent Workspace does not exist
    deleted = frappe.db.sql(
        """
        DELETE ws FROM `tabWorkspace Shortcut` ws
        LEFT JOIN `tabWorkspace` w ON ws.parent = w.name
        WHERE ws.parenttype IS NULL AND w.name IS NULL
        """,
    )
    deleted_count = frappe.db.sql("SELECT ROW_COUNT()")[0][0]
    print(f"  Deleted {deleted_count} orphaned Workspace Shortcut records")
