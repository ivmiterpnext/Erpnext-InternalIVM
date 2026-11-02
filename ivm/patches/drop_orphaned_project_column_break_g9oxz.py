"""
Drop an orphaned Project custom field: custom_column_break_g9oxz.

This Column Break was absent from every fixture source file (custom_field.json,
ivm/custom/project.json) and from the field_order Property Setter, but still
existed live in the database. Frappe splices any field missing from
field_order in right after its insert_after anchor, so this stray empty
Column Break rendered as a permanently empty 4th column on the Project form's
Details tab. Column Break fields have no database column of their own, so
there is nothing to drop beyond the Custom Field record itself.
"""

import frappe

ORPHAN_FIELD = "Project-custom_column_break_g9oxz"


def execute():
	if frappe.db.exists("Custom Field", ORPHAN_FIELD):
		frappe.delete_doc("Custom Field", ORPHAN_FIELD, ignore_permissions=True, force=True)
		frappe.db.commit()
		print(f"  Deleted Custom Field: {ORPHAN_FIELD}")
	else:
		print(f"  Custom Field {ORPHAN_FIELD} does not exist — skipping")
