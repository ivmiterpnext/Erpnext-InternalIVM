import frappe


def add_barcode_to_item(item_doc, barcode, barcode_type="CODE-39", uom="Nos"):
    """
    Add a barcode to an item's barcode table if it doesn't already exist.
    """
    if not barcode:
        return False

    for existing_barcode in item_doc.barcodes:
        if existing_barcode.barcode == barcode:
            return False

    item_doc.append("barcodes", {
        "barcode": barcode,
        "barcode_type": barcode_type,
        "uom": uom
    })

    return True


@frappe.whitelist()
def lookup_item_by_barcode(barcode):
    """
    Lookup item by barcode.
    Checks Item Barcode table, falls back to Item Code.
    Item Barcode is a child table with no permissions, so we use SQL directly.
    """
    if not barcode:
        return None

    item_code = frappe.db.sql("""
        SELECT parent 
        FROM `tabItem Barcode` 
        WHERE barcode = %s 
        LIMIT 1
    """, (barcode,), as_dict=False)

    if item_code and len(item_code) > 0:
        return item_code[0][0]

    if frappe.db.exists("Item", barcode):
        return barcode

    return None
