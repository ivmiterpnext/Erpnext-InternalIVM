from ivm.warehouse.services.barcode_manager import add_barcode_to_item


def before_save(item_doc, method=None):
    if item_doc.item_code:
        add_barcode_to_item(item_doc, item_doc.item_code, "CODE-39", "Nos")
