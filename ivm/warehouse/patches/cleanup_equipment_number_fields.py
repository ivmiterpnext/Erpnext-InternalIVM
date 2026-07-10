import frappe


def execute():
    """Clean up equipment number fields after Text -> Data conversion.

    The machine_name, mac_address, and prose_number fields were changed from
    Text (longtext) to Data (varchar 140). Frappe handles the schema change
    automatically during migrate. This patch trims whitespace-only values that
    were stored as defaults in the old Text fields.

    Note: mac_address was later renamed to lan_mac_address; the column may
    not exist by this name on fresh installs, so each field is checked before
    running the update.
    """
    fields = ("machine_name", "mac_address", "prose_number")

    for field in fields:
        if not frappe.db.has_column("Warehouse Request", field):
            continue
        frappe.db.sql(
            f"""
            UPDATE `tabWarehouse Request`
            SET `{field}` = NULL
            WHERE TRIM(`{field}`) = ''
            """
        )

    frappe.db.commit()
    print("Cleaned up whitespace-only values in equipment number fields.")
