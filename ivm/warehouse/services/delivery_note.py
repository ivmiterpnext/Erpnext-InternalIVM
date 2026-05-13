import frappe
from ivm.warehouse.services.stock_entry import get_stock_entry_items_from_warehouse_request


def create_delivery_note_from_warehouse_request(warehouse_request_name):
    """
    Automatically create and submit a Delivery Note for a Shipping Request.

    Returns the Delivery Note name, or None if no items were found.
    """
    existing_dn = frappe.db.get_value(
        "Delivery Note",
        {"custom_related_warehouse_request": warehouse_request_name, "docstatus": ["!=", 2]},
        "name",
    )

    if existing_dn:
        frappe.msgprint(
            f'Delivery Note <a href="/app/delivery-note/{existing_dn}">{existing_dn}</a> '
            "already exists for this Warehouse Request.",
            title="Delivery Note Exists",
            indicator="blue",
        )
        return existing_dn

    wr = frappe.get_doc("Warehouse Request", warehouse_request_name)

    items = get_stock_entry_items_from_warehouse_request(warehouse_request_name)
    if not items:
        frappe.log_error(
            title="Delivery Note Auto-Creation Skipped",
            message=f"No stock entry items found for Warehouse Request {warehouse_request_name}. "
                    "Delivery Note was not created.",
        )
        return None

    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )

    customer = wr.account
    if not customer:
        frappe.throw(
            f"Warehouse Request {warehouse_request_name} has no Account (Customer) set. "
            "Cannot create a Delivery Note without a customer.",
            title="Missing Customer",
        )

    dn = frappe.new_doc("Delivery Note")
    dn.company = company
    dn.customer = customer
    dn.custom_related_warehouse_request = warehouse_request_name

    for item_data in items:
        dn.append("items", {
            "item_code": item_data["item_code"],
            "item_name": item_data["item_name"],
            "description": item_data.get("description") or item_data["item_name"],
            "qty": item_data["qty"],
            "uom": item_data["uom"],
            "stock_uom": item_data.get("stock_uom") or item_data["uom"],
            "conversion_factor": item_data.get("conversion_factor", 1),
            "warehouse": item_data.get("warehouse"),
            "rate": item_data.get("rate", 0),
        })

    dn.insert(ignore_permissions=True)
    dn.submit()

    frappe.msgprint(
        f'Delivery Note <a href="/app/delivery-note/{dn.name}">{dn.name}</a> '
        "has been created and submitted automatically.",
        title="Delivery Note Created",
        indicator="green",
    )

    return dn.name
