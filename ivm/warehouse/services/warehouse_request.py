import json
from typing import Any, NamedTuple

import frappe

from ivm.warehouse.services.machine import apply_machine_data, fetch_machine
from ivm.warehouse.services.pick_list import create_pick_list, delete_draft_pick_list, serialize_pick_list

_COMMON_DETAIL_FIELDS = [
	"machine_name",
	"connectivity_type",
	"connectivity_device_quantity",
	"label_color",
	"offline_sales",
	"smartscreen",
	"workflow",
	"serial_validation",
	"home_screen_logo",
	"machine_type_id",
	"casters",
	"notes",
]

_LOCKER_SYNC_FIELDS = [
	"lan_ports",
	"plug_type",
	"interior_lighting",
	"bin_door_type",
	"3d_printed",
]

_VAULT_SYNC_FIELDS = [f for f in _LOCKER_SYNC_FIELDS if f != "3d_printed"]


class _TableConfig(NamedTuple):
	reason: str
	doctype: str
	extra_fields: list[str]


# Add a new entry here when a new deployment detail table is introduced.
_TABLE_CONFIG: dict[str, _TableConfig] = {
	"custom_deployment_smartstation_details": _TableConfig(
		reason="Build Machine",
		doctype="Deployment SmartStation Details",
		extra_fields=["card_reader_type", "machine_key"],
	),
	"custom_deployment_smartlocker_details": _TableConfig(
		reason="Build Locker",
		doctype="Deployment SmartLocker Details",
		extra_fields=_LOCKER_SYNC_FIELDS,
	),
	"custom_deployment_smartsync_details": _TableConfig(
		reason="Build Locker",
		doctype="Deployment SmartSync Details",
		extra_fields=_LOCKER_SYNC_FIELDS,
	),
	"custom_deployment_smartvault_details": _TableConfig(
		reason="Build Vault",
		doctype="Deployment SmartVault Details",
		extra_fields=_VAULT_SYNC_FIELDS,
	),
	"custom_deployment_smartcenter_details": _TableConfig(
		reason="Build Kiosk",
		doctype="Deployment SmartCenter Details",
		extra_fields=[
			"kiosk_options",
			"kvm_switch_options",
			"monitor_options",
			"network_options",
			"network_port_in_bins",
			"interior_kiosk_lighting",
			"locker_bin_door_type",
			"countertop_color",
			"ada_side_table",
			"kiosk_side_for_table",
			"monitor_mount",
			"power_connections_in_bins",
		],
	),
}


class _PendingRequest(NamedTuple):
	row: Any
	icorp_data: dict[str, Any]


@frappe.whitelist()
def create_build_requests_from_detail_rows(project_name: str, detail_table: str) -> dict:
	"""
	Create one Warehouse Request per row in the given detail child table.
	All-or-nothing: if any iCorp lookup fails, no requests are created.
	"""
	if detail_table not in _TABLE_CONFIG:
		frappe.throw(f"Unknown detail table: {detail_table}")

	config = _TABLE_CONFIG[detail_table]
	reason = config.reason
	project = frappe.get_doc("Project", project_name)
	rows = project.get(detail_table) or []

	if not rows:
		frappe.throw(f"No rows found in {detail_table} on project {project_name}.")

	customer_name = project.get("customer")
	if not customer_name:
		frappe.throw("Customer is not set on this Project. Cannot look up machines in iCorp.")

	client_id = frappe.db.get_value("Customer", customer_name, "icorp_client_id")
	if not client_id:
		frappe.throw(
			f'Customer "{customer_name}" does not have an iCorp Client ID. '
			"Please set it on the Customer record before generating build requests."
		)

	fields_to_copy = _COMMON_DETAIL_FIELDS + config.extra_fields

	# Pass 1 — validate all rows before creating anything.
	pending: list[_PendingRequest] = []
	failed: list[str] = []
	skipped = 0

	for row in rows:
		machine_name = row.get("machine_name") or row.name

		if frappe.db.exists(
			"Warehouse Request",
			{
				"related_project": project_name,
				"request_reason": reason,
				"machine_name": machine_name,
			},
		):
			skipped += 1
			continue

		icorp_data = fetch_machine(machine_name, client_id)
		if icorp_data is None:
			failed.append(machine_name)
			continue

		pending.append(_PendingRequest(row=row, icorp_data=icorp_data))

	if failed:
		return {"created": [], "skipped": skipped, "failed": failed}

	# Pass 2 — all machines validated, safe to create.
	project_display = project.get("project_name") or project_name
	location_name = project_display.split(" - ")[0] if " - " in project_display else project_display

	created: list[str] = []

	for item in pending:
		row = item.row
		icorp_data = item.icorp_data
		machine_name = row.get("machine_name") or row.name

		wr = frappe.new_doc("Warehouse Request")
		wr.related_project = project_name
		wr.request_reason = reason
		wr.schema_version = 2
		wr.source_detail_doctype = config.doctype
		wr.source_detail_row = row.name
		wr.customer = customer_name
		wr.locale = project.get("locale")
		wr.machine_ownership_status = project.get("machine_ownership_status")
		wr.contact = project.get("contact_name")
		wr.subject = f"{location_name} - {reason} [{machine_name}]"

		for field in fields_to_copy:
			value = row.get(field)
			if value is not None and value != "":
				setattr(wr, field, value)

		apply_machine_data(wr, icorp_data)
		wr.insert(ignore_permissions=True)
		created.append(wr.name)

	return {"created": created, "skipped": skipped, "failed": []}


@frappe.whitelist()
def get_or_create_warehouse_request_pick_list(warehouse_request: str) -> dict:
	"""Get the existing Pick List for a Warehouse Request, or create one if none exists."""
	pick_list = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")

	if pick_list:
		return serialize_pick_list(frappe.get_doc("Pick List", pick_list))

	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	pl_name = create_pick_list(company)
	frappe.db.set_value("Warehouse Request", warehouse_request, "pick_list", pl_name)

	default_target_warehouse = _get_default_target_warehouse()
	if default_target_warehouse:
		frappe.db.set_value("Pick List", pl_name, "parent_warehouse", default_target_warehouse)

	return {
		"pick_list": pl_name,
		"submitted": False,
		"target_warehouse": default_target_warehouse,
		"items": [],
	}


@frappe.whitelist()
def get_warehouse_request_linked_docs(warehouse_request):
	"""Return linked Pick List, Stock Entry, and Delivery Note in a single call."""
	pick_list = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")
	if not pick_list:
		return {"pick_list": None, "pick_list_submitted": False, "stock_entry": None, "delivery_note": None}

	docstatus = frappe.db.get_value("Pick List", pick_list, "docstatus")

	stock_entry = None
	delivery_note = None

	if docstatus == 1:
		stock_entry = frappe.db.get_value(
			"Stock Entry", {"pick_list": pick_list, "docstatus": ["!=", 2]}, "name"
		)
		delivery_note = frappe.db.get_value(
			"Delivery Note",
			{"custom_related_warehouse_request": warehouse_request, "docstatus": ["!=", 2]},
			"name",
		)

	return {
		"pick_list": pick_list,
		"pick_list_submitted": docstatus == 1,
		"stock_entry": stock_entry,
		"delivery_note": delivery_note,
	}


@frappe.whitelist()
def reset_warehouse_request_pick_list(warehouse_request):
	"""Delete the draft Pick List for a Warehouse Request and clear the link."""
	pl_name = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")

	if not pl_name:
		return {"success": False, "message": "No pick list linked"}

	frappe.db.set_value("Warehouse Request", warehouse_request, "pick_list", None)
	delete_draft_pick_list(pl_name)

	return {"success": True}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def warehouse_request_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link field search query that shows 'WR-XXXXX - Subject' in dropdowns."""
	return frappe.db.sql(
		"""
        SELECT
            name,
            CASE
                WHEN subject IS NOT NULL AND subject != ''
                THEN CONCAT(name, ' - ', subject)
                ELSE name
            END as description
        FROM `tabWarehouse Request`
        WHERE
            (name LIKE %(txt)s OR subject LIKE %(txt)s)
            AND docstatus < 2
        ORDER BY modified DESC
        LIMIT %(start)s, %(page_len)s
    """,
		{"txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


DEFAULT_TARGET_WAREHOUSE = "Build In Progress - I"


def _get_default_target_warehouse():
	if frappe.db.exists("Warehouse", DEFAULT_TARGET_WAREHOUSE):
		return DEFAULT_TARGET_WAREHOUSE
	return None


@frappe.whitelist()
def create_shipping_request_from_build(build_warehouse_request):
	"""Create a Shipping Request linked to a completed Build request.

	Requires the Build WR to be in 'Crated - Ready to Ship' status with a
	submitted Pick List.

	Returns the existing Shipping Request name if one
	already exists for this Build.
	"""
	build_wr = frappe.get_doc("Warehouse Request", build_warehouse_request)

	if not build_wr.request_reason or not build_wr.request_reason.startswith("Build"):
		frappe.throw(f"Warehouse Request {build_warehouse_request} is not a Build request.")

	if build_wr.status != "Crated - Ready to Ship":
		frappe.throw(
			f"Warehouse Request {build_warehouse_request} must be in "
			"'Crated - Ready to Ship' status to create a Shipping Request."
		)

	if not build_wr.pick_list:
		frappe.throw(f"Warehouse Request {build_warehouse_request} has no Pick List.")

	pl_docstatus = frappe.db.get_value("Pick List", build_wr.pick_list, "docstatus")
	if pl_docstatus != 1:
		frappe.throw(f"Pick List {build_wr.pick_list} must be submitted before creating a Shipping Request.")

	existing = frappe.db.get_value(
		"Warehouse Request",
		{"source_build_request": build_warehouse_request, "request_reason": "Shipping Request"},
		"name",
	)
	if existing:
		frappe.msgprint(
			f'Shipping Request <a href="/app/warehouse-request/{existing}">{existing}</a> '
			"already exists for this Build.",
			title="Shipping Request Exists",
			indicator="blue",
		)
		return existing

	shipping_wr = frappe.new_doc("Warehouse Request")
	shipping_wr.request_reason = "Shipping Request"
	shipping_wr.source_build_request = build_warehouse_request
	shipping_wr.related_project = build_wr.related_project
	shipping_wr.customer = build_wr.customer
	shipping_wr.status = "New"
	shipping_wr.subject = f"Ship {build_wr.request_reason} - {build_wr.name}"
	shipping_wr.insert(ignore_permissions=True)

	return shipping_wr.name


# Following will be replaced and push directly to iCorp
def _build_equipment_info_description(wr) -> str:
	lines = [
		f"Equipment Information Has Been Added to {wr.name}",
		"",
		f"Project: {wr.subject or ''} {wr.machine_name or ''}",
		"",
		f"Machine Name: {wr.machine_name or ''}",
		f"PROSE Number: {wr.prose_number or ''}",
		f"Serial Number: {wr.serial_number or ''}",
		f"LAN MAC Address: {wr.lan_mac_address or ''}",
		f"WiFi MAC Address: {wr.wifi_mac_address or ''}",
	]

	rfid_rows = wr.get("rfid_settings") or []
	if rfid_rows:
		lines.append("")
		for idx, row in enumerate(rfid_rows, start=1):
			lines.append(
				f"RFID Setting {idx}: "
				f"Facility Code Start {row.facility_code_start_position}, "
				f"Facility Code Length {row.facility_code_length}, "
				f"Employee ID Start {row.employee_id_start_position}, "
				f"Employee ID Length {row.employee_id_length}, "
				f"Target Number Base {row.target_number_base}, "
				f"Bit Size {row.bit_size}, "
				f"Bit Reverse {'Yes' if row.bit_reverse_feature else 'No'}"
			)

	return "<br>".join(lines)


@frappe.whitelist()
def get_equipment_info_task(warehouse_request):
	"""Return the existing 'add machine info' Task linked to this Warehouse Request, if any."""
	return frappe.db.get_value(
		"Task",
		{"custom_warehouse_request": warehouse_request, "type": "add machine info"},
		"name",
	)


@frappe.whitelist()
def send_equipment_info_to_ics(warehouse_request):
	"""Create the 'Add Equipment Information' Task for a schema v2 Warehouse Request,
	pulling data from the single-machine schema fields instead of the legacy
	numbered/ordinal fields used by schema_version == 1.
	"""
	wr = frappe.get_doc("Warehouse Request", warehouse_request)

	if (wr.schema_version or 0) < 2:
		frappe.throw("This action is only available for the schema v2 Warehouse Request layout.")

	if not (wr.request_reason or "").startswith("Build"):
		frappe.throw("This action is only available for Build requests.")

	existing = get_equipment_info_task(warehouse_request)
	if existing:
		return existing

	task = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": f"Add Equipment Information into CSS for {wr.machine_name} and {wr.customer}",
			"status": "Open",
			"type": "add machine info",
			"custom_customer": wr.customer,
			"project": wr.related_project,
			"custom_warehouse_request": wr.name,
			"custom_assigned_to": wr.owner,
			"description": _build_equipment_info_description(wr),
		}
	)
	task.insert(ignore_permissions=True)

	return task.name


def render_machine_details_html(doc):
	"""Jinja helper (registered in hooks.py) that renders the Warehouse Request's
	linked machine-detail child row as a read-only HTML block for print/PDF output.

	Mirrors the section/column layout defined in the child doctype's meta, producing
	the same Bootstrap grid markup that Frappe's standard print format
	(standard.html + standard_macros.html) uses for every other section on the page,
	so this block is visually indistinguishable from the rest of the printed document.
	"""
	doctype = doc.get("source_detail_doctype")
	name = doc.get("source_detail_row")
	if not doctype or not name or not frappe.db.exists(doctype, name):
		return ""

	meta = frappe.get_meta(doctype)
	row = frappe.get_doc(doctype, name)

	sections = _build_print_sections(meta, row)
	if not sections:
		return ""

	return "".join(_render_print_section(s) for s in sections)


def _build_print_sections(meta, row):
	"""Walk the child doctype's meta.fields and group renderable fields into
	a list of sections, each containing a list of columns, each containing a
	list of (label, value_html, full_width) tuples.
	"""
	sections = []
	current_section = {"label": "", "columns": [[]], "hidden": False}

	for df in meta.fields:
		if df.fieldtype in ("Tab Break", "Section Break"):
			if _section_has_data(current_section):
				sections.append(current_section)
			current_section = {
				"label": df.label or "",
				"columns": [[]],
				"hidden": bool(df.hidden),
			}
			continue

		if df.fieldtype == "Column Break":
			current_section["columns"].append([])
			continue

		if current_section["hidden"] or df.hidden:
			continue

		field_html = _render_field_for_print(df, row)
		if field_html is not None:
			current_section["columns"][-1].append(field_html)

	if _section_has_data(current_section):
		sections.append(current_section)

	return sections


def _section_has_data(section):
	if section["hidden"]:
		return False
	return any(col for col in section["columns"])


def _render_field_for_print(df, row):
	"""Render a single field as a (label, value_html, full_width) tuple,
	or return None if the field should be skipped.
	"""
	value = row.get(df.fieldname)

	if df.fieldname == "bins_data":
		bin_html = _render_bins_table(value)
		if not bin_html:
			return None
		return (df.label or "Bins", bin_html, True)

	if df.fieldtype == "Check":
		if not value:
			return None
		display_value = (
			"<svg viewBox='0 0 16 16' fill='transparent' stroke='#1F272E' stroke-width='2' "
			"xmlns='http://www.w3.org/2000/svg' style='width: 12px; height: 12px; margin-top: 5px;'>"
			"<path d='M2 9.66667L5.33333 13L14 3' stroke-miterlimit='10' "
			"stroke-linecap='round' stroke-linejoin='round'></path></svg>"
		)
		return (df.label or df.fieldname, display_value, False)

	if value in (None, ""):
		return None

	display_value = frappe.utils.escape_html(str(value))
	return (df.label or df.fieldname, display_value, False)


def _render_print_section(section):
	"""Render a section dict as HTML matching standard.html's markup:
	  <div class="row section-break">
	    <div class="col-xs-{N} column-break">
	      ...fields...
	    </div>
	  </div>
	"""
	non_empty_columns = [col for col in section["columns"] if col]
	if not non_empty_columns:
		return ""

	no_of_cols = len(non_empty_columns)
	col_width = 12 // no_of_cols

	columns_html = []
	for col_fields in non_empty_columns:
		fields_html = "".join(
			_render_field_row(label, value_html, full_width, no_of_cols)
			for label, value_html, full_width in col_fields
		)
		columns_html.append(
			f"<div class='col-xs-{col_width} column-break'>{fields_html}</div>"
		)

	return f"<div class='row section-break'>{''.join(columns_html)}</div>"


def _render_field_row(label, value_html, full_width=False, no_of_cols=2):
	"""Render a single field row matching standard_macros.html::render_field_with_label.

	When no_of_cols >= 3, uses full-width (col-xs-12) for both label and value,
	matching Frappe's own behavior for 3+ column sections.
	"""
	escaped_label = frappe.utils.escape_html(label)

	if full_width:
		return (
			"<div class='row data-field'>"
			f"<div class='col-xs-12'><label>{escaped_label}</label>{value_html}</div>"
			"</div>"
		)

	if no_of_cols >= 3:
		return (
			"<div class='row data-field'>"
			f"<div class='col-xs-12'><label>{escaped_label}: </label></div>"
			f"<div class='col-xs-12 value'>{value_html}</div>"
			"</div>"
		)

	return (
		"<div class='row data-field'>"
		f"<div class='col-xs-5'><label>{escaped_label}: </label></div>"
		f"<div class='col-xs-7 value'>{value_html}</div>"
		"</div>"
	)


def _render_bins_table(bins_json):
	try:
		bins = json.loads(bins_json) if bins_json else []
	except (TypeError, ValueError):
		bins = []

	if not bins:
		return "<div class='text-muted'>No bins configured</div>"

	rows = []
	for b in bins:
		bin_type = b.get("bin_type", "")
		num = b.get("bin_number", "") if bin_type == "Storage" else "N/A"
		rows.append(
			f"<tr><td style='width:33.33%;'>{frappe.utils.escape_html(bin_type)}</td>"
			f"<td style='width:33.33%;'>{frappe.utils.escape_html(str(num))}</td>"
			f"<td style='width:33.33%;'>{frappe.utils.escape_html(str(b.get('bin_size', '')))}</td></tr>"
		)

	return (
		"<table class='table table-bordered table-condensed' style='table-layout:fixed;'>"
		"<thead><tr><th style='width:33.33%;'>Type</th><th style='width:33.33%;'>#</th>"
		"<th style='width:33.33%;'>Size (Inches)</th></tr></thead>"
		f"<tbody>{''.join(rows)}</tbody></table>"
	)
