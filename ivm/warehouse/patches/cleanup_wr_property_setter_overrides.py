"""
Delete orphaned Property Setters, a dead Custom Field, and dead DocType Links
on Warehouse Request that were created via Customize Form and shipped in
ivm/ivm/custom/warehouse_request.json before that file was removed from the
repo (see docs/agent/changelog.md). Since sync_customizations() only adds/
updates records present in a custom file and never deletes records absent
from it, removing the file alone left these 22 Property Setters, 1 Custom
Field, and 2 DocType Links live in the DB, silently overriding the DocType
JSON's own values on every site that ever ran sync_customizations() against
that file.

Each Property Setter was reviewed individually against the current DocType
JSON before being marked for removal:

- due_date-in_list_view, subject-in_list_view, status-in_list_view,
  related_case-in_list_view, related_project-in_list_view,
  request_reason-in_list_view: redundant — DocType JSON already sets
  in_list_view=1 natively on subject/status/related_case/related_project/
  request_reason; due_date's PS override wasn't even rendering (some other
  ordering issue), and in_list_view is being added natively where wanted.
- main-quick_entry: PS forced quick_entry=1; confirmed not wanted, DocType
  JSON leaves it unset (defaults to 0).
- main-allow_import: PS forced allow_import=1; no data source to import
  from, confirmed not wanted.
- main-track_changes: redundant — DocType JSON already sets track_changes=1
  natively.
- naming_series-hidden: redundant — DocType JSON already sets hidden=1
  natively on the naming_series field.
- naming_series-in_global_search: PS forced in_global_search=1 on a field
  whose value is always the constant "WR - " on every record — indexing it
  is meaningless, confirmed not wanted.
- naming_series-options: redundant — DocType JSON's naming_series field
  options is being updated to match this value directly (see the sibling
  DocType JSON change in this same deploy).
- main-autoname / main-naming_rule: PS forced format-based autoname
  ("format:WR - {#####}" / "Expression"). Existing WR documents are already
  named "WR - #####" (with the space) — renaming existing documents was
  assessed as too risky (breaks every raw-string cross-reference). Instead
  the DocType JSON's own naming_series field default/options are updated to
  "WR - " (see sibling DocType JSON change), keeping autoname="naming_series"
  / naming_rule="By \"Naming Series\" field" as already set natively, which
  reproduces the same "WR - #####" format going forward without an override.
- main-default_view: PS cleared it to null; DocType JSON already natively
  sets default_view="List", which should take effect once the PS is gone.
- main-title_field: PS cleared it to ""; DocType JSON already natively sets
  title_field="subject", which should take effect once the PS is gone.
- main-editable_grid: PS forced editable_grid=0; DocType JSON already
  natively sets editable_grid=1, confirmed as the desired behavior — PS
  override removed so the native value takes effect.
- main-links_order: references two DocType Link records (see below) that
  are being deleted in this same patch; the ordering value is meaningless
  without them.
- warehouse_request_name-default / -in_global_search / -in_list_view /
  -unique: warehouse_request_name is a ghost field — it has no DB column
  and no Custom Field record on dev, and was fully removed from the DocType
  JSON's own fields/field_order in commit 9b0a442 ("one giant leap for IVM
  Frappe Portal Kind") with no corresponding cleanup patch ever written for
  the orphaned Property Setters or (on environments where it lingered) the
  Custom Field record itself.

Also deletes:
- Custom Field "Warehouse Request-warehouse_request_name": same ghost field
  as above; confirmed absent on dev but may still exist on environments
  that never had it cleaned up.
- DocType Link records "5621044d22" (Issue, related_warehouse_request) and
  "ab408c5519" (Task, custom_warehouse_request): created via Customize Form,
  which persists DocType Link rows with parenttype="Customize Form" instead
  of "DocType" — Frappe's sidebar link renderer only reads links with
  parenttype="DocType", so these have never actually rendered anything on
  the document sidebar since they were created. Dead weight.

A defensive dynamic lookup for a stale field_order Property Setter is also
included (matches by doc_type+property rather than hardcoded name) as a
no-op safety net — the primary field_order cleanup already happened via
ivm.warehouse.patches.delete_stale_wr_field_order_property_setter, and this
site's DB no longer has an entry for it, but the lookup is cheap insurance
in case a different-named record was independently recreated on some other
site via Customize Form after that patch ran.

Safe to run repeatedly (idempotent).
"""

import frappe

PROPERTY_SETTERS = [
	"Warehouse Request-due_date-in_list_view",
	"Warehouse Request-main-allow_import",
	"Warehouse Request-main-autoname",
	"Warehouse Request-main-default_view",
	"Warehouse Request-main-editable_grid",
	"Warehouse Request-main-links_order",
	"Warehouse Request-main-naming_rule",
	"Warehouse Request-main-quick_entry",
	"Warehouse Request-main-title_field",
	"Warehouse Request-main-track_changes",
	"Warehouse Request-naming_series-hidden",
	"Warehouse Request-naming_series-in_global_search",
	"Warehouse Request-naming_series-options",
	"Warehouse Request-related_case-in_list_view",
	"Warehouse Request-related_project-in_list_view",
	"Warehouse Request-request_reason-in_list_view",
	"Warehouse Request-status-in_list_view",
	"Warehouse Request-subject-in_list_view",
	"Warehouse Request-warehouse_request_name-default",
	"Warehouse Request-warehouse_request_name-in_global_search",
	"Warehouse Request-warehouse_request_name-in_list_view",
	"Warehouse Request-warehouse_request_name-unique",
]

DOCTYPE_LINKS = [
	"5621044d22",
	"ab408c5519",
]


def execute():
	for name in PROPERTY_SETTERS:
		if frappe.db.exists("Property Setter", name):
			frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
			print(f"  Deleted Property Setter: {name}")
		else:
			print(f"  Property Setter {name} does not exist — skipping")

	cf_name = "Warehouse Request-warehouse_request_name"
	if frappe.db.exists("Custom Field", cf_name):
		frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
		print(f"  Deleted Custom Field: {cf_name}")
	else:
		print(f"  Custom Field {cf_name} does not exist — skipping")

	for link_name in DOCTYPE_LINKS:
		if frappe.db.exists("DocType Link", link_name):
			frappe.delete_doc("DocType Link", link_name, ignore_permissions=True, force=True)
			print(f"  Deleted DocType Link: {link_name}")
		else:
			print(f"  DocType Link {link_name} does not exist — skipping")

	# Defensive no-op safety net — see docstring.
	stale_field_order_name = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Warehouse Request", "property": "field_order"},
		"name",
	)
	if stale_field_order_name:
		frappe.delete_doc("Property Setter", stale_field_order_name, ignore_permissions=True, force=True)
		print(f"  Deleted stale field_order Property Setter: {stale_field_order_name}")

	frappe.db.commit()
	frappe.clear_cache(doctype="Warehouse Request")
