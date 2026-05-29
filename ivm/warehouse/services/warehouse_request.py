import frappe
from ivm.warehouse.services.pick_list import create_pick_list, delete_draft_pick_list


@frappe.whitelist()
def get_or_create_warehouse_request_pick_list(warehouse_request):
    """
    Get the existing Pick List for a Warehouse Request, or create one if none exists.
    Returns the Pick List name, its current items, and whether it is editable (draft).
    """
    pick_list = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")

    if pick_list:
        pl_doc = frappe.get_doc("Pick List", pick_list)
        is_draft = pl_doc.docstatus == 0

        items = []
        for loc in pl_doc.locations:
            if is_draft:
                available_qty = frappe.db.get_value(
                    "Bin", {"item_code": loc.item_code, "warehouse": loc.warehouse}, "actual_qty"
                ) or 0
            else:
                available_qty = loc.stock_qty

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

    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
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
    """
    Return the linked Pick List, Stock Entry, and Delivery Note for a Warehouse Request
    in a single call. Used by the form to populate View buttons without multiple round trips.
    """
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
    """Delete the draft Pick List for a Warehouse Request and clear the link, allowing a fresh start."""
    pl_name = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")

    if not pl_name:
        return {"success": False, "message": "No pick list linked"}

    frappe.db.set_value("Warehouse Request", warehouse_request, "pick_list", None)
    delete_draft_pick_list(pl_name)

    return {"success": True}


@frappe.whitelist()
def create_shipping_request_from_build(build_warehouse_request):
    """
    Create a Shipping Request Warehouse Request from a completed Build WR.

    The new Shipping Request links back to the Build via `source_build_request`
    so that its Delivery Note can be populated from the Build's Pick List items.
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
        frappe.throw(
            f"Pick List {build_wr.pick_list} must be submitted before "
            "creating a Shipping Request."
        )

    # Check if a Shipping Request already exists for this Build
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
    shipping_wr.account = build_wr.account
    shipping_wr.status = "New"
    shipping_wr.subject = f"Ship {build_wr.request_reason} - {build_wr.name}"
    shipping_wr.insert(ignore_permissions=True)

    return shipping_wr.name


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def warehouse_request_query(doctype, txt, searchfield, start, page_len, filters):
    """Custom query for Warehouse Request link fields — shows name and subject."""
    return frappe.db.sql("""
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
        ORDER BY modified DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        'txt': f'%{txt}%',
        'start': start,
        'page_len': page_len,
    })

DEFAULT_TARGET_WAREHOUSE = "Build In Progress - I"

def _get_default_target_warehouse():
    """Return the default target warehouse for new Pick Lists, or None if it doesn't exist."""
    if frappe.db.exists("Warehouse", DEFAULT_TARGET_WAREHOUSE):
        return DEFAULT_TARGET_WAREHOUSE
    return None