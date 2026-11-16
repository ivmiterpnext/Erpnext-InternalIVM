"""
Delete the stale `Email Account-main-field_order` Property Setter.

Root cause: a Customize Form save on Email Account back on 2023-09-21,
made before Frappe added Tab Break fields (`incoming_popimap_tab`,
`outgoing_tab`) to this doctype's layout, froze a field order that predates
those tabs. When Frappe's meta reconciliation (frappe/model/meta.py
_update_field_order_based_on_insert_after) splices the missing tab-break
fields back in using their `insert_after` hints, `enable_incoming` ends up
relocated to render *inside* the Incoming tab -- the tab it's supposed to
gate. Net effect: the "Enable Incoming" checkbox becomes invisible on the
form once unchecked, with no way to re-check it from the UI (discovered
during the 2026-11 "Invalid Mail Server" incident).

Same class of bug as the Task and Warehouse Request field_order
regressions already fixed in ivm.patches.cleanup_orphaned_customizations
and ivm.warehouse.patches.cleanup_wr_property_setter_overrides. No evidence
this reordering was ever intentional -- deleting it restores Frappe's
native, tab-safe default layout.

Safe to run repeatedly (idempotent).
"""

import frappe


def execute():
	name = "Email Account-main-field_order"
	if frappe.db.exists("Property Setter", name):
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
		print(f"  Deleted Property Setter: {name}")
	else:
		print(f"  Property Setter {name} does not exist -- skipping")

	frappe.clear_cache(doctype="Email Account")
