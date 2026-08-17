import frappe


def execute():
    """
    Create a Non-Inventory Shipment item for use in non-stock shipments.
    This item is used as a placeholder in Delivery Notes for shipments
    containing only non-stock items (e.g., printed labels).
    """
    item_code = "Non-Inventory Shipment"

    # Check if item already exists (idempotent)
    if frappe.db.exists("Item", item_code):
        print(f"Item '{item_code}' already exists. Skipping creation.")
        return {"status": "skipped", "reason": "Item already exists"}

    # Create the item with exact name to bypass autoname() naming series override
    doc = frappe.new_doc("Item")
    doc.name = item_code
    doc.flags.name_set = True
    doc.item_code = item_code
    doc.item_name = "Non-Inventory Shipment"
    doc.item_group = "Services"
    doc.is_stock_item = 0
    doc.stock_uom = "Nos"
    doc.disabled = 0

    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    print(f"Created Item '{item_code}'")
    print(f"  - item_name: {doc.item_name}")
    print(f"  - item_group: {doc.item_group}")
    print(f"  - is_stock_item: {doc.is_stock_item}")
    print(f"  - stock_uom: {doc.stock_uom}")

    return {
        "status": "created",
        "item_code": item_code,
        "item_name": doc.item_name,
        "item_group": doc.item_group,
        "is_stock_item": doc.is_stock_item,
        "stock_uom": doc.stock_uom
    }
