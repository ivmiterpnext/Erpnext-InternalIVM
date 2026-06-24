import frappe


def execute():
    """Rename the 'account' field to 'customer' on Warehouse Request.

    This is a pre_model_sync patch so the column rename happens before
    Frappe tries to sync the new schema (which expects 'customer').
    """
    table = "tabWarehouse Request"
    columns = [c.column for c in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`", as_dict=True)]

    has_account = "account" in columns
    has_customer = "customer" in columns

    if has_account and not has_customer:
        # Normal case: rename the column directly.
        frappe.db.sql(f"ALTER TABLE `{table}` CHANGE `account` `customer` varchar(140)")
    elif has_account and has_customer:
        # Edge case: both columns exist (e.g. partial prior run).
        # Copy any data from account -> customer where customer is empty, then drop account.
        frappe.db.sql(
            f"UPDATE `{table}` SET `customer` = `account` "
            "WHERE (`customer` IS NULL OR `customer` = '') "
            "AND `account` IS NOT NULL AND `account` != ''"
        )
        frappe.db.sql(f"ALTER TABLE `{table}` DROP COLUMN `account`")
    # If only customer exists, nothing to do.

    frappe.db.commit()

    # Clean up the old property setter that was set via fixtures.
    if frappe.db.exists("Property Setter", "Warehouse Request-account-in_list_view"):
        frappe.db.delete(
            "Property Setter",
            {"name": "Warehouse Request-account-in_list_view"},
        )
