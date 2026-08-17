import frappe


def execute():
    """Rename the 'internal_notes' field to 'notes' on Warehouse Request.

    This is a pre_model_sync patch so the column rename happens before
    Frappe tries to sync the new schema (which expects 'notes').
    """
    table = "tabWarehouse Request"
    columns = [c.column for c in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`", as_dict=True)]

    has_old = "internal_notes" in columns
    has_new = "notes" in columns

    if has_old and not has_new:
        # Simple rename: old column exists, new doesn't
        frappe.db.sql_ddl(f"ALTER TABLE `{table}` CHANGE `internal_notes` `notes` longtext")
    elif has_old and has_new:
        # Both exist: merge data from old to new (if new is empty), then drop old
        frappe.db.sql(
            f"UPDATE `{table}` SET `notes` = `internal_notes` "
            "WHERE (`notes` IS NULL OR `notes` = '') "
            "AND `internal_notes` IS NOT NULL AND `internal_notes` != ''"
        )
        frappe.db.commit()
        frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `internal_notes`")
