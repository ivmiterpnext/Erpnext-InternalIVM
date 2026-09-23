import re
from io import BytesIO
from urllib.parse import quote

import frappe
import xlsxwriter
from erpnext.stock.doctype.pick_list.pick_list import create_stock_entry as _create_stock_entry
from frappe.desk.utils import provide_binary_file
from frappe.utils.xlsxutils import ILLEGAL_CHARACTERS_RE, get_sanitized_sheet_name, make_xlsx
from xlsxwriter.url import Url
from xlsxwriter.utility import cell_autofit_width

from ivm.warehouse.services.inventory import get_available_qty


def _get_draft_pick_list(pick_list):
	"""Load a Pick List and ensure it is still a draft."""
	pl_doc = frappe.get_doc("Pick List", pick_list)
	if pl_doc.docstatus != 0:
		frappe.throw(f"Pick List {pick_list} is already submitted and cannot be modified")
	return pl_doc


def create_pick_list(company):
	"""
	Create and save a new draft Pick List for material transfer.

	Returns: document's name.
	"""
	pl_doc = frappe.new_doc("Pick List")
	pl_doc.company = company
	pl_doc.purpose = "Material Transfer"
	pl_doc.pick_manually = 1
	pl_doc.insert(ignore_permissions=True)
	return pl_doc.name


def delete_draft_pick_list(pick_list):
	"""Delete a draft Pick List. Raises if already submitted."""
	if frappe.db.get_value("Pick List", pick_list, "docstatus") != 0:
		frappe.throw("Only draft pick lists can be deleted")
	frappe.delete_doc("Pick List", pick_list, ignore_permissions=True)


def _to_float(value):
	return float(value) if isinstance(value, str) else value


def _find_location_row_by_name(pl_doc, row_name):
	return next((loc for loc in pl_doc.locations if loc.name == row_name), None)


@frappe.whitelist()
def add_item_to_pick_list(pick_list, item_code, warehouse, qty, item_name=None, uom=None):
	"""Add an item to a Pick List's locations, or increment qty if already present."""
	qty = _to_float(qty)

	pl_doc = _get_draft_pick_list(pick_list)

	existing = next(
		(loc for loc in pl_doc.locations if loc.item_code == item_code and loc.warehouse == warehouse),
		None,
	)

	if existing:
		existing.qty += qty
		existing.picked_qty = existing.qty
		pl_doc.save()
		return {"row_name": existing.name, "qty": existing.qty}

	if not item_name or not uom:
		fetched_name, fetched_uom = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom"])
		item_name = item_name or fetched_name
		uom = uom or fetched_uom

	available_qty = get_available_qty(item_code, warehouse)

	pl_doc.append(
		"locations",
		{
			"item_code": item_code,
			"item_name": item_name,
			"warehouse": warehouse,
			"qty": qty,
			"picked_qty": qty,
			"stock_qty": available_qty,
			"uom": uom,
			"stock_uom": uom,
			"conversion_factor": 1,
		},
	)
	pl_doc.save()

	new_row = pl_doc.locations[-1]
	return {"row_name": new_row.name, "qty": new_row.qty}


@frappe.whitelist()
def remove_pick_list_item(pick_list, row_name):
	"""Remove a row from the Pick List locations child table."""
	pl_doc = _get_draft_pick_list(pick_list)
	if _find_location_row_by_name(pl_doc, row_name) is None:
		frappe.throw(f"Row {row_name} not found in Pick List {pick_list}", exc=frappe.DoesNotExistError)
	pl_doc.locations = [loc for loc in pl_doc.locations if loc.name != row_name]
	pl_doc.save()
	return {"success": True}


@frappe.whitelist()
def update_pick_list_item_qty(pick_list, row_name, qty):
	"""Update the qty of a specific Pick List location row."""
	qty = _to_float(qty)

	pl_doc = _get_draft_pick_list(pick_list)
	loc = _find_location_row_by_name(pl_doc, row_name)
	if loc is None:
		frappe.throw(f"Row {row_name} not found in Pick List {pick_list}", exc=frappe.DoesNotExistError)
	loc.qty = qty
	loc.picked_qty = qty
	pl_doc.save()
	return {"success": True}


@frappe.whitelist()
def clear_pick_list_items(pick_list):
	"""Remove all rows from a draft Pick List."""
	pl_doc = _get_draft_pick_list(pick_list)
	pl_doc.locations = []
	pl_doc.save()
	return {"success": True}


def serialize_pick_list(pl_doc) -> dict:
	"""Build a frontend-friendly representation of an existing Pick List."""
	is_draft = pl_doc.docstatus == 0

	items = []
	for loc in pl_doc.locations:
		available_qty = get_available_qty(loc.item_code, loc.warehouse) if is_draft else loc.stock_qty

		items.append(
			{
				"row_name": loc.name,
				"item_code": loc.item_code,
				"item_name": loc.item_name,
				"warehouse": loc.warehouse,
				"qty": loc.qty,
				"picked_qty": loc.picked_qty,
				"uom": loc.uom,
				"available_qty": available_qty,
			}
		)

	stock_entry = frappe.db.get_value(
		"Stock Entry", {"pick_list": pl_doc.name, "docstatus": ["!=", 2]}, "name"
	)

	return {
		"pick_list": pl_doc.name,
		"submitted": pl_doc.docstatus == 1,
		"target_warehouse": pl_doc.parent_warehouse,
		"stock_entry": stock_entry,
		"items": items,
	}


def _apply_target_warehouse(pl_doc, target_warehouse):
	if target_warehouse:
		pl_doc.parent_warehouse = target_warehouse
		pl_doc.save()


def _build_stock_entry_from_pick_list(pl_doc, target_warehouse):
	stock_entry_dict = _create_stock_entry(frappe.as_json(pl_doc.as_dict()))
	if target_warehouse:
		for item in stock_entry_dict.get("items", []):
			if not item.get("t_warehouse"):
				item["t_warehouse"] = target_warehouse
	return frappe.get_doc(stock_entry_dict)


def _link_warehouse_request(stock_entry, pick_list):
	warehouse_request = frappe.db.get_value("Warehouse Request", {"pick_list": pick_list}, "name")
	if warehouse_request:
		stock_entry.custom_warehouse_request = warehouse_request


@frappe.whitelist()
def submit_pick_list(pick_list, target_warehouse=None):
	"""Submit the Pick List and create a draft Stock Entry from it."""
	pl_doc = _get_draft_pick_list(pick_list)
	_apply_target_warehouse(pl_doc, target_warehouse)
	pl_doc.submit()

	stock_entry = _build_stock_entry_from_pick_list(pl_doc, target_warehouse)
	_link_warehouse_request(stock_entry, pick_list)
	stock_entry.insert()

	return {"pick_list": pl_doc.name, "stock_entry": stock_entry.name}


def _resolve_item_rate(item_code, warehouse):
	"""Resolve a per-item valuation rate: prefer the Bin's rate for this
	specific warehouse (reflects actual stock value at that location),
	falling back to the Item's global valuation_rate if the Bin has none
	or doesn't exist."""
	bin_rate = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate")
	if bin_rate:
		return bin_rate
	return frappe.db.get_value("Item", item_code, "valuation_rate") or 0


def get_pick_list_cost_rows(pick_list):
	"""Build cost rows for a Pick List: one dict per location row plus
	rate/amount, for use in the cost Excel export."""
	pl_doc = frappe.get_doc("Pick List", pick_list)

	rows = []
	for loc in pl_doc.locations:
		rate = _resolve_item_rate(loc.item_code, loc.warehouse)
		qty = loc.qty or 0
		rows.append(
			{
				"item_code": loc.item_code,
				"item_name": loc.item_name,
				"warehouse": loc.warehouse,
				"qty": qty,
				"uom": loc.uom,
				"rate": rate,
				"amount": qty * rate,
			}
		)
	return rows


def _get_related_project(pick_list):
	"""Resolve the Project associated with a Pick List via its Warehouse
	Request (Pick List has no direct Project link of its own). Returns
	(project_id, project_name), both None if no Warehouse Request links to
	this pick list or none has a related_project set. If more than one
	Warehouse Request references the same pick list (not expected in normal
	use), the first match is taken with no error."""
	project_id = frappe.db.get_value(
		"Warehouse Request",
		{"pick_list": pick_list, "related_project": ["is", "set"]},
		"related_project",
	)
	if not project_id:
		return None, None
	project_name = frappe.db.get_value("Project", project_id, "project_name")
	return project_id, project_name


FILENAME_ILLEGAL_CHARS_RE = re.compile(r'[\\/:*?"<>|]')

ACCOUNTING_NUMBER_FORMAT = '_(* #,##0.00_);_(* \\(#,##0.00\\);_(* "-"??_);_(@_)'


def _build_item_link(item_code: str, item_name: str) -> Url:
	"""Build a clickable link for an Inventory Part cell, pointing at that
	item's Desk page on the current site, displaying '{item_code}: {item_name}'
	as the visible text (same text shown before this became a link).
	Uses frappe.utils.get_url() rather than a hardcoded domain so the link
	always points at whichever site actually generated the export."""
	display_text = ILLEGAL_CHARACTERS_RE.sub("", f"{item_code}: {item_name}")
	link = Url(f"{frappe.utils.get_url()}/desk/item/{quote(item_code)}")
	link.text = display_text
	return link


def _sanitize_filename_label(label: str) -> str:
	return FILENAME_ILLEGAL_CHARS_RE.sub("", label).strip()


def _resolve_pick_list_label(pick_list: str) -> str:
	"""Resolve a human-readable label for a Pick List's export filename:
	prefer the linked Warehouse Request's machine name, then its related
	Project (Deployment) ID, then fall back to the Pick List's own docname."""
	wr = frappe.db.get_value(
		"Warehouse Request",
		{"pick_list": pick_list},
		["machine_names", "machine_name", "related_project"],
		as_dict=True,
	)
	label = None
	if wr:
		label = wr.machine_names or wr.machine_name or wr.related_project
	return _sanitize_filename_label(label) if label else pick_list


def _pixels_to_character_width(pixels: float) -> float:
	"""Convert a pixel width to Excel's character-unit column width, using
	the same formula xlsxwriter's own worksheet.autofit() uses internally.
	Reimplemented here (rather than reused) because autofit() itself is a
	no-op in constant_memory mode, which this export relies on."""
	max_digit_width = 7.0
	padding = 5.0
	if pixels <= 12:
		return pixels / (max_digit_width + padding)
	return (pixels - padding) / max_digit_width


def _autofit_column_width(values, minimum_width: float) -> float:
	"""Compute the character-unit column width needed to fit the widest of
	`values` without truncation, never going narrower than `minimum_width`."""
	max_pixels = max((cell_autofit_width(v) for v in values), default=0)
	return max(minimum_width, _pixels_to_character_width(max_pixels))


def _build_pick_list_excel_payload(pick_list: str) -> dict:
	"""Build the data/styles/column widths/filename for a Pick List's Excel
	export: Inventory Part / Qty Picked / Price / Total columns (with
	spacer columns B/D/F), no bold/fill styling, matching the company's
	standard Pick List template. Total column uses Excel formulas
	(=Cn*En per row, =SUM(...) for the grand total) with cached values
	explicitly supplied alongside each formula, so the Total column always
	displays the correct value immediately on open, regardless of Protected
	View, Enable Editing, or Excel's calculation mode. The last item row
	gets a thin bottom border across columns A-G, matching the template's
	rule line before the total. Grand total row displays a red warning
	message in column A if any item's Price resolved to 0, since a $0 rate
	is otherwise indistinguishable from a real cost value. Returns
	`last_item_row_idx` so the caller can scope an AutoFilter to the header
	+ item rows only, excluding the blank spacer/total rows below."""
	rows = get_pick_list_cost_rows(pick_list)

	data = [["Inventory Part ", None, "Qty Picked", None, "Price", None, "Total"]]

	first_data_row = len(data) + 1  # 1-based Excel row number of first item row

	for row in rows:
		data.append(
			[
				_build_item_link(row["item_code"], row["item_name"]),
				None,
				row["qty"],
				None,
				row["rate"],
				None,
				None,
			]
		)

	last_data_row = first_data_row + len(rows) - 1

	total_cells = []

	for i, excel_row in enumerate(range(first_data_row, last_data_row + 1)):
		formula = f"=C{excel_row}*E{excel_row}"
		data[i + 1][6] = formula
		total_cells.append((i + 1, formula, rows[i]["amount"]))

	data.append([None] * 7)  # blank spacer row before total

	has_missing_price = bool(rows) and any(row["rate"] == 0 for row in rows)

	if rows:
		grand_total_row_idx = len(data)
		grand_total_formula = f"=SUM(G{first_data_row}:G{last_data_row})"
		warning_text = "* Missing Price data — Total may be understated" if has_missing_price else None
		data.append([warning_text, None, None, None, None, None, grand_total_formula])
		total_cells.append((grand_total_row_idx, grand_total_formula, sum(row["amount"] for row in rows)))
	else:
		data.append([None] * 7)
		grand_total_row_idx = None

	ALIGN_STYLE_ID = 0
	CURRENCY_STYLE_ID = 1
	BORDER_STYLE_ID = 2
	HYPERLINK_STYLE_ID = 3
	WARNING_STYLE_ID = 4

	styles = {
		"styles": [
			{"align": "left", "valign": "vcenter"},
			{"num_format": ACCOUNTING_NUMBER_FORMAT},
			{"bottom": 1},
			{"font_color": "blue", "underline": 1, "align": "left", "valign": "vcenter"},
			{"font_color": "red"},
		],
		"column_styles": {
			0: [ALIGN_STYLE_ID],
			4: [CURRENCY_STYLE_ID],
			6: [CURRENCY_STYLE_ID],
		},
		"cell_styles": {},
	}

	for row_idx in range(1, len(rows) + 1):
		styles["cell_styles"][(row_idx, 0)] = [HYPERLINK_STYLE_ID]

	last_item_row_idx = None
	if rows:
		# 0-based row index of the last item row (row 0 in `data` is the header)
		last_item_row_idx = len(rows)
		for col_idx in range(7):
			if col_idx == 0:
				styles["cell_styles"][(last_item_row_idx, 0)] = [HYPERLINK_STYLE_ID, BORDER_STYLE_ID]
			else:
				styles["cell_styles"][(last_item_row_idx, col_idx)] = [BORDER_STYLE_ID]

	if has_missing_price:
		styles["cell_styles"][(grand_total_row_idx, 0)] = [WARNING_STYLE_ID]

	inventory_part_texts = ["Inventory Part "] + [f"{row['item_code']}: {row['item_name']}" for row in rows]

	column_widths = [
		_autofit_column_width(inventory_part_texts, 57.86),
		None,
		10.14,
		None,
		11,
		None,
		12,
	]

	filename = f"{_resolve_pick_list_label(pick_list)} - Pick List"

	return {
		"data": data,
		"column_widths": column_widths,
		"styles": styles,
		"filename": filename,
		"last_item_row_idx": last_item_row_idx,
		"total_cells": total_cells,
		"has_missing_price": has_missing_price,
	}


@frappe.whitelist()
def export_pick_list_cost_excel(pick_list):
	"""Stream an .xlsx file of item costs for a Pick List, matching the
	company's standard Pick List template: Inventory Part / Qty Picked /
	Price / Total columns, no header identifier rows, no bold styling,
	and a sort/filter AutoFilter on the header row scoped to the item
	rows (excluding the blank spacer/total rows). Total column formulas
	are written with cached values so the column displays correctly
	immediately on open. Column widths for columns that also carry a
	column-level style (Inventory Part, Price, Total) are re-applied
	after make_xlsx() runs, working around a core bug where make_xlsx()'s
	column-style loop calls ws.set_column() without re-passing the width
	set by its earlier column-width loop, silently resetting it to
	xlsxwriter's internal default."""
	if not frappe.has_permission("Pick List", "read", pick_list):
		frappe.throw("Not permitted", frappe.PermissionError)

	payload = _build_pick_list_excel_payload(pick_list)

	xlsx_stream = BytesIO()
	wb = xlsxwriter.Workbook(xlsx_stream)

	make_xlsx(
		payload["data"],
		payload["filename"],
		wb=wb,
		column_widths=payload["column_widths"],
		styles=payload["styles"],
	)

	ws = wb.get_worksheet_by_name(get_sanitized_sheet_name(payload["filename"]))

	styled_column_formats = {
		0: wb.add_format({"align": "left", "valign": "vcenter"}),
		4: wb.add_format({"num_format": ACCOUNTING_NUMBER_FORMAT}),
		6: wb.add_format({"num_format": ACCOUNTING_NUMBER_FORMAT}),
	}
	for col_idx, width in enumerate(payload["column_widths"]):
		if width and col_idx in styled_column_formats:
			ws.set_column(col_idx, col_idx, width, styled_column_formats[col_idx])

	last_row_total_format = wb.add_format({"num_format": ACCOUNTING_NUMBER_FORMAT, "bottom": 1})

	for row_idx, formula, value in payload["total_cells"]:
		cell_format = (
			last_row_total_format if row_idx == payload["last_item_row_idx"] else styled_column_formats[6]
		)
		ws.write_formula(row_idx, 6, formula, cell_format, value)

	if payload["last_item_row_idx"] is not None:
		ws.autofilter(0, 0, payload["last_item_row_idx"], 6)

	wb.close()
	xlsx_stream.seek(0)

	provide_binary_file(payload["filename"], "xlsx", xlsx_stream.getvalue())
