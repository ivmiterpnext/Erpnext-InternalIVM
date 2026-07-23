import frappe


def execute():
    doctypes_with_connectivity_type = [
        ("Deployment SmartStation Details", "connectivity_type"),
        ("Deployment SmartSync Details", "connectivity_type"),
        ("Deployment SmartLocker Details", "connectivity_type"),
        ("Deployment SmartVault Details", "connectivity_type"),
        ("Project", "connectivity_type"),
        ("Issue", "connectivity_type"),
    ]
    for doctype, fieldname in doctypes_with_connectivity_type:
        frappe.db.sql(
            f"UPDATE `tab{doctype}` SET `{fieldname}` = '' WHERE `{fieldname}` = '--None--'"
        )

    frappe.db.sql("DELETE FROM `tabCell Carrier` WHERE `cell_carrier` = '--None--'")

    if frappe.db.exists("Connectivity Type", "--None--"):
        frappe.delete_doc(
            "Connectivity Type", "--None--", ignore_permissions=True, force=True
        )

    frappe.db.commit()
