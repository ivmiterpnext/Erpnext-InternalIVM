import frappe


def execute():
    """Rename the 'mac_address' field to 'lan_mac_address' on Warehouse Request.

    This is a pre_model_sync patch so the column rename happens before
    Frappe tries to sync the new schema (which expects 'lan_mac_address').
    """
    table = "tabWarehouse Request"
    columns = [c.column for c in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`", as_dict=True)]

    has_old = "mac_address" in columns
    has_new = "lan_mac_address" in columns

    if has_old and not has_new:
        # Normal case: rename the column directly.
        frappe.db.sql(f"ALTER TABLE `{table}` CHANGE `mac_address` `lan_mac_address` varchar(140)")
    elif has_old and has_new:
        # Edge case: both columns exist (e.g. partial prior run).
        # Copy any data from mac_address -> lan_mac_address where lan_mac_address is empty, then drop mac_address.
        frappe.db.sql(
            f"UPDATE `{table}` SET `lan_mac_address` = `mac_address` "
            "WHERE (`lan_mac_address` IS NULL OR `lan_mac_address` = '') "
            "AND `mac_address` IS NOT NULL AND `mac_address` != ''"
        )
        frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `mac_address`")
    # If only lan_mac_address exists, nothing to do.

    frappe.db.commit()
