import frappe

from ivm.warehouse.services.inventory import get_available_qty
from erpnext.stock.doctype.pick_list.pick_list import create_stock_entry as _create_stock_entry


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

    pl_doc.append("locations", {
        "item_code": item_code,
        "item_name": item_name,
        "warehouse": warehouse,
        "qty": qty,
        "picked_qty": qty,
        "stock_qty": available_qty,
        "uom": uom,
        "stock_uom": uom,
        "conversion_factor": 1,
    })
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

        items.append({
            "row_name": loc.name,
            "item_code": loc.item_code,
            "item_name": loc.item_name,
            "warehouse": loc.warehouse,
            "qty": loc.qty,
            "picked_qty": loc.picked_qty,
            "uom": loc.uom,
            "available_qty": available_qty,
        })

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
