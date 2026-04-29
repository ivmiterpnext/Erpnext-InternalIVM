import frappe


@frappe.whitelist()
def get_item_with_warehouse(item_code, parent_warehouse='All Warehouses - I'):
    """Get item details and all leaf warehouses with stock under parent_warehouse, ordered by qty."""
    item_code, item_name, stock_uom = frappe.db.get_value("Item", item_code, ["item_code", "item_name", "stock_uom"])

    def get_leaf_warehouses(parent):
        warehouses = []
        children = frappe.get_all("Warehouse",
            filters={"parent_warehouse": parent, "disabled": 0},
            fields=["name", "is_group"],
        )
        for child in children:
            if child.is_group:
                warehouses.extend(get_leaf_warehouses(child.name))
            else:
                warehouses.append(child.name)
        return warehouses

    warehouses_with_stock = []
    for warehouse in get_leaf_warehouses(parent_warehouse):
        stock_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
        if stock_qty and stock_qty > 0:
            warehouses_with_stock.append({"warehouse": warehouse, "available_qty": stock_qty})

    warehouses_with_stock.sort(key=lambda x: x["available_qty"], reverse=True)

    return {
        "item_code": item_code,
        "item_name": item_name,
        "stock_uom": stock_uom,
        "warehouses": warehouses_with_stock
    }
