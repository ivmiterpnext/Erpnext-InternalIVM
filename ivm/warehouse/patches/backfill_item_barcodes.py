import frappe
from ivm.warehouse.services.barcode_manager import add_barcode_to_item


def execute():
    """
    Backfills existing item's barcode table with item codes to allow scanning.
    """
    items = frappe.get_all("Item", fields=["name", "item_code"])
    print(f"Found {len(items)} items to process\n")

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for item_data in items:
        try:
            item = frappe.get_doc("Item", item_data.name)

            was_added = add_barcode_to_item(item, item.item_code, "CODE-39", "Nos")

            if was_added:
                item.save()
                updated_count += 1
                if updated_count <= 20:  # Show first 20
                    print(f"  ✓ Added barcode to {item.item_code}")
                elif updated_count % 50 == 0:  # Progress every 50
                    print(f"  ... processed {updated_count} items")
            else:
                skipped_count += 1
        except Exception as e:
            error_count += 1
            print(f"  ✗ Error with {item_data.name}: {e}")

    frappe.db.commit()

    print(f"\n{'='*50}")
    print("Summary:")
    print(f"  Total items: {len(items)}")
    print(f"  Updated: {updated_count}")
    print(f"  Skipped (already had barcode): {skipped_count}")
    print(f"  Errors: {error_count}")
    print(f"{'='*50}")

    return {
        "total": len(items),
        "updated": updated_count,
        "skipped": skipped_count,
        "errors": error_count
    }
