import frappe


@frappe.whitelist()
def get_stock_entry_items_from_warehouse_request(warehouse_request):
    """
    Get all items from submitted Stock Entries related to a Warehouse Request.
    
    Returns: items grouped by item_code and target warehouse.
    """
    entry_names = frappe.get_all("Stock Entry",
        filters={"docstatus": 1, "stock_entry_type": "Material Transfer", "custom_warehouse_request": warehouse_request},
        pluck="name",
    )
    if not entry_names:
        return []

    rows = frappe.get_all("Stock Entry Detail",
        filters={"parent": ["in", entry_names]},
        fields=["item_code", "t_warehouse", "qty", "uom", "basic_rate"],
    )

    items_dict = {}
    for row in rows:
        key = (row.item_code, row.t_warehouse)
        if key in items_dict:
            items_dict[key]["qty"] += row.qty
        else:
            item_name, description, stock_uom = frappe.db.get_value(
                "Item", row.item_code, ["item_name", "description", "stock_uom"]
            )
            items_dict[key] = {
                "item_code": row.item_code,
                "item_name": item_name,
                "description": description or item_name,
                "qty": row.qty,
                "uom": row.uom,
                "stock_uom": stock_uom,
                "conversion_factor": 1,
                "warehouse": row.t_warehouse,
                "rate": row.basic_rate or 0,
                "price_list_rate": row.basic_rate or 0,
            }

    return list(items_dict.values())
