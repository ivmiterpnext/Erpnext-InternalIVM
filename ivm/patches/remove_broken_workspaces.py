import frappe

def execute():
    # 1. Delete broken/orphaned custom Desktop Icon launchers
    for name in ("IVM", "Accounts Receivable", "ERPNext Integrations", "Tools", "Payables"):
        if frappe.db.exists("Desktop Icon", name):
            frappe.delete_doc("Desktop Icon", name, ignore_permissions=True, force=True)

    # 2. Delete broken/orphaned custom Workspace Sidebars (cascades their Workspace Sidebar Item children)
    for name in ("IVM", "Accounting", "Accounts Receivable", "ERPNext Integrations", "Tools"):
        if frappe.db.exists("Workspace Sidebar", name):
            frappe.delete_doc("Workspace Sidebar", name, ignore_permissions=True, force=True)

    # 3. Delete the IVM Workspace page itself (cascades its Workspace Shortcut children)
    if frappe.db.exists("Workspace", "IVM"):
        frappe.delete_doc("Workspace", "IVM", ignore_permissions=True, force=True)

    # 4. Reparent the 8 dangling "Support"-child workspaces under "IT"
    if frappe.db.exists("Workspace", "IT"):
        for name in (
            "Change Request", "Desktop Support", "Offboarding", "Onboarding",
            "Permission Change", "Receivable", "Reconfiguration", "Support Queue",
        ):
            if frappe.db.exists("Workspace", name):
                frappe.db.set_value("Workspace", name, "parent_page", "IT")
