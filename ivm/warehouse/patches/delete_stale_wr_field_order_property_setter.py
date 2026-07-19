import frappe


def execute():
    """Delete stale field_order Property Setter for Warehouse Request.

    A Property Setter with property='field_order' on Warehouse Request was
    created by the Customize Form UI at some point and silently overrides the
    DocType JSON's field_order during Meta.sort_fields(). Any fields added
    directly via file edits after its creation are missing from its list,
    causing scrambled field rendering (wrong order, collapsed columns).

    Fixed manually on dev (2026-07-10). This patch applies the same fix
    during migrate on any site that still has the stale record.
    """
    name = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "Warehouse Request", "property": "field_order"},
        "name",
    )
    if not name:
        print("No stale field_order Property Setter found — nothing to do.")
        return

    frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
    frappe.clear_cache(doctype="Warehouse Request")
    print(f"Deleted stale Property Setter '{name}' and cleared Warehouse Request cache.")
