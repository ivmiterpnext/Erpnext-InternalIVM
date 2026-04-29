import json
import frappe

BUILD_IN_PROGRESS_WAREHOUSE = "Build In Progress - I"


@frappe.whitelist()
def has_stock_entries_for_warehouse_request(warehouse_request):
    """Check if submitted stock entries already exist for this warehouse request."""
    return bool(frappe.get_all("Stock Entry",
        filters={"docstatus": 1, "stock_entry_type": "Material Transfer", "custom_warehouse_request": warehouse_request},
        limit=1,
    ))


@frappe.whitelist()
def create_stock_entry_from_scan(warehouse_request, items, target_warehouse):
    """Create a Material Transfer Stock Entry from scanned items."""
    if isinstance(items, str):
        items = json.loads(items)

    stock_entry = frappe.new_doc("Stock Entry")
    stock_entry.stock_entry_type = "Material Transfer"
    stock_entry.custom_warehouse_request = warehouse_request
    stock_entry.remarks = f"Material Transfer for Warehouse Request: {warehouse_request}"

    for item in items:
        stock_entry.append("items", {
            "item_code": item.get("item_code"),
            "qty": item.get("qty", 1),
            "uom": item.get("uom"),
            "s_warehouse": item.get("source_warehouse"),
            "t_warehouse": target_warehouse,
            "transfer_qty": item.get("qty", 1)
        })

    stock_entry.insert()
    stock_entry.submit()
    return stock_entry.name


@frappe.whitelist()
def get_stock_entry_items_from_warehouse_request(warehouse_request):
    """
    Get all items from submitted Stock Entries related to a Warehouse Request.
    Used by Delivery Note to fetch items from the Build In Progress warehouse.
    """
    entries = frappe.get_all("Stock Entry",
        filters={"docstatus": 1, "stock_entry_type": "Material Transfer", "custom_warehouse_request": warehouse_request},
        fields=["name"],
    )
    if not entries:
        return []

    items_dict = {}
    for entry in entries:
        doc = frappe.get_doc("Stock Entry", entry.name)
        for item in doc.items:
            if item.t_warehouse != BUILD_IN_PROGRESS_WAREHOUSE:
                continue
            if item.item_code in items_dict:
                items_dict[item.item_code]["qty"] += item.qty
            else:
                item_name, description, stock_uom = frappe.db.get_value(
                    "Item", item.item_code, ["item_name", "description", "stock_uom"]
                )
                items_dict[item.item_code] = {
                    "item_code": item.item_code,
                    "item_name": item_name,
                    "description": description or item_name,
                    "qty": item.qty,
                    "uom": item.uom,
                    "stock_uom": stock_uom,
                    "conversion_factor": 1,
                    "warehouse": BUILD_IN_PROGRESS_WAREHOUSE,
                    "rate": item.basic_rate or 0,
                    "price_list_rate": item.basic_rate or 0,
                }

    return list(items_dict.values())
