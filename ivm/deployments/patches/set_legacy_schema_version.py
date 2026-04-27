import frappe


def execute():
    if not frappe.db.has_column("Project", "custom_schema_version"):
        frappe.db.sql("ALTER TABLE `tabProject` ADD COLUMN `custom_schema_version` INT DEFAULT NULL")
        frappe.db.commit()
        print("Added custom_schema_version column.")

    affected = frappe.db.sql(
        "SELECT COUNT(*) FROM `tabProject` WHERE `custom_schema_version` IS NULL OR `custom_schema_version` = 0",
    )[0][0]

    if not affected:
        print("No Projects needed schema version backfill.")
        return

    frappe.db.sql(
        "UPDATE `tabProject` SET `custom_schema_version` = 1 WHERE `custom_schema_version` IS NULL OR `custom_schema_version` = 0"
    )
    frappe.db.commit()

    frappe.db.sql("ALTER TABLE `tabProject` ALTER COLUMN `custom_schema_version` SET DEFAULT 2")
    frappe.db.commit()

    print(f"Set custom_schema_version=1 on {affected} Project(s).")
