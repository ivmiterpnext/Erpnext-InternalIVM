import frappe


def _get_top_level_warehouse_map(warehouse_names):
    """Map each given leaf warehouse name to its top-level ancestor (the warehouse directly under the tree root)."""
    parent_map = {
        w.name: w.parent_warehouse
        for w in frappe.get_all("Warehouse", fields=["name", "parent_warehouse"])
    }
    result = {}
    for wh in warehouse_names:
        node = wh
        while True:
            parent = parent_map.get(node)
            if not parent:
                result[wh] = node
                break
            grandparent = parent_map.get(parent)
            if not grandparent:
                result[wh] = node
                break
            node = parent
    return result


def _get_leaf_warehouses(parent_warehouse):
    """Get all leaf (non-group) warehouses under parent_warehouse. If parent_warehouse itself is a leaf, return it."""
    is_group = frappe.db.get_value("Warehouse", parent_warehouse, "is_group")
    if not is_group:
        return [parent_warehouse]
    warehouses = []
    for child in frappe.get_all("Warehouse", filters={"parent_warehouse": parent_warehouse, "disabled": 0}, fields=["name", "is_group"]):
        if child.is_group:
            warehouses.extend(_get_leaf_warehouses(child.name))
        else:
            warehouses.append(child.name)
    return warehouses


@frappe.whitelist()
def get_item_with_warehouse(item_code, parent_warehouse='All Warehouses - I'):
    """Get item details and all leaf warehouses with stock under parent_warehouse, ordered by qty."""
    item_code, item_name, stock_uom = frappe.db.get_value("Item", item_code, ["item_code", "item_name", "stock_uom"])

    warehouses_with_stock = []
    for warehouse in _get_leaf_warehouses(parent_warehouse):
        stock_qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
        if stock_qty and stock_qty > 0:
            warehouses_with_stock.append({"warehouse": warehouse, "available_qty": stock_qty})

    warehouses_with_stock.sort(key=lambda x: x["available_qty"], reverse=True)

    top_level_map = _get_top_level_warehouse_map([w["warehouse"] for w in warehouses_with_stock])
    for w in warehouses_with_stock:
        w["top_level_warehouse"] = top_level_map.get(w["warehouse"], w["warehouse"])

    return {
        "item_code": item_code,
        "item_name": item_name,
        "stock_uom": stock_uom,
        "warehouses": warehouses_with_stock
    }


@frappe.whitelist()
def search_items_by_name(txt, parent_warehouse='All Warehouses - I', limit=20):
    """Search items by partial name match with available stock under parent_warehouse, ordered by total qty."""
    if not txt or len(txt) < 2:
        return []
    leaf_warehouses = _get_leaf_warehouses(parent_warehouse)
    if not leaf_warehouses:
        return []
    return frappe.db.sql("""
        SELECT b.item_code, i.item_name, i.stock_uom, SUM(b.actual_qty) as total_qty
        FROM `tabBin` b
        INNER JOIN `tabItem` i ON i.item_code = b.item_code
        WHERE b.warehouse IN %(warehouses)s
          AND b.actual_qty > 0
          AND i.disabled = 0
          AND i.item_name LIKE %(txt)s
        GROUP BY b.item_code
        ORDER BY total_qty DESC
        LIMIT %(limit)s
    """, {"warehouses": leaf_warehouses, "txt": f"%{txt}%", "limit": int(limit)}, as_dict=True)
