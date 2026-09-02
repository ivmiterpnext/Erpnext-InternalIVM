import frappe

# Root warehouse for stock lookups. Update if the company abbreviation changes.
ROOT_WAREHOUSE = "All Warehouses - I"


def get_available_qty(item_code, warehouse):
    """Get actual stock qty for an item in a specific warehouse (Bin.actual_qty), or 0 if none."""
    return frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0


def _get_top_level_warehouse_map(warehouse_names):
    """Map each given leaf warehouse name to its top-level ancestor (child of the tree root)."""
    if not warehouse_names:
        return {}

    rows = frappe.db.sql("""
        SELECT leaf.name AS leaf_name, ancestor.name AS top_level
        FROM `tabWarehouse` leaf
        JOIN `tabWarehouse` ancestor
            ON leaf.lft >= ancestor.lft AND leaf.rgt <= ancestor.rgt
        JOIN `tabWarehouse` root
            ON ancestor.parent_warehouse = root.name
        WHERE leaf.name IN %(names)s
          AND (root.parent_warehouse IS NULL OR root.parent_warehouse = '')
    """, {"names": warehouse_names}, as_dict=True)

    return {r.leaf_name: r.top_level for r in rows}


def _get_leaf_warehouses(parent_warehouse):
    """Get all leaf (non-group) warehouses under parent_warehouse. If parent_warehouse itself is a leaf, return it."""
    is_group = frappe.db.get_value("Warehouse", parent_warehouse, "is_group")
    if not is_group:
        return [parent_warehouse]

    lft, rgt = frappe.db.get_value("Warehouse", parent_warehouse, ["lft", "rgt"])
    return frappe.get_all("Warehouse",
        filters={
            "lft": [">", lft],
            "rgt": ["<", rgt],
            "is_group": 0,
            "disabled": 0,
        },
        pluck="name",
    )


@frappe.whitelist()
def get_item_with_warehouse(item_code, parent_warehouse=None):
    """Get item details and all leaf warehouses with stock under parent_warehouse, ordered by qty."""
    if not parent_warehouse:
        parent_warehouse = ROOT_WAREHOUSE

    item = frappe.db.get_value("Item", item_code, ["item_code", "item_name", "stock_uom"], as_dict=True)
    if not item:
        frappe.throw(f"Item {item_code} not found", frappe.DoesNotExistError)

    leaf_warehouses = _get_leaf_warehouses(parent_warehouse)
    if not leaf_warehouses:
        return {**item, "warehouses": []}

    warehouses_with_stock = frappe.get_all("Bin",
        filters={
            "item_code": item_code,
            "warehouse": ["in", leaf_warehouses],
            "actual_qty": [">", 0],
        },
        fields=["warehouse", "actual_qty as available_qty"],
        order_by="actual_qty desc",
    )

    if warehouses_with_stock:
        top_level_map = _get_top_level_warehouse_map([w["warehouse"] for w in warehouses_with_stock])
        for w in warehouses_with_stock:
            w["top_level_warehouse"] = top_level_map.get(w["warehouse"], w["warehouse"])

    return {**item, "warehouses": warehouses_with_stock}


@frappe.whitelist()
def search_items_by_name(txt, parent_warehouse=None, limit=20):
    """Search items by partial name match with available stock under parent_warehouse, ordered by total qty."""
    if not txt or len(txt) < 2:
        return []
    if not parent_warehouse:
        parent_warehouse = ROOT_WAREHOUSE
    leaf_warehouses = _get_leaf_warehouses(parent_warehouse)
    if not leaf_warehouses:
        return []
    limit = min(int(limit), 100)
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
    """, {"warehouses": leaf_warehouses, "txt": f"%{txt}%", "limit": limit}, as_dict=True)
