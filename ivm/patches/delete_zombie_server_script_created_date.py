"""
Delete zombie Server Script: 'Created Date'.

This Server Script record is broken (invalid script body) and was never
properly integrated. It should have been removed long ago.

Must run AFTER populate_ivm_module_on_customizations (which explicitly
excludes this record by name to avoid tagging it).
"""

import frappe


def execute():
	if frappe.db.exists("Server Script", "Created Date"):
		frappe.delete_doc("Server Script", "Created Date", ignore_permissions=True, force=True)
		print("  Deleted zombie Server Script: Created Date")
	else:
		print("  Server Script 'Created Date' does not exist — skipping")
