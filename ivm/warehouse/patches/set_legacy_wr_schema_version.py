import frappe


def execute():
    if not frappe.db.has_column("Warehouse Request", "schema_version"):
        frappe.db.sql("ALTER TABLE `tabWarehouse Request` ADD COLUMN `schema_version` INT DEFAULT NULL")
        frappe.db.commit()
        print("Added schema_version column to Warehouse Request.")

    affected = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabWarehouse Request` WHERE `schema_version` IS NULL OR `schema_version` = 0",
    )[0][0]

    if not affected:
        print("No Warehouse Requests needed schema version backfill.")
        return

    frappe.db.sql(
        "UPDATE `tabWarehouse Request` SET `schema_version` = 1 WHERE `schema_version` IS NULL OR `schema_version` = 0"
    )
    frappe.db.commit()

    frappe.db.sql("ALTER TABLE `tabWarehouse Request` ALTER COLUMN `schema_version` SET DEFAULT 2")
    frappe.db.commit()

    print(f"Set schema_version=1 on {affected} Warehouse Request(s).")
