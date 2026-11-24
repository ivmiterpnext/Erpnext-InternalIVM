"""
Drop the orphaned Project.shipping_address column.

This field was deleted from Project's metadata at some point (no Custom
Field record exists for it in fixtures or any site DB), but the DB column
was never dropped, and ivm/public/js/doctype/Project.js had a dead
frm.set_query("shipping_address", ...) call still referencing it. The
field was intended as a Link to the Address doctype but was never
populated in practice (0% adoption across all Projects).
"""

import frappe


def execute():
	if frappe.db.has_column("Project", "shipping_address"):
		frappe.db.sql_ddl("ALTER TABLE `tabProject` DROP COLUMN `shipping_address`")
