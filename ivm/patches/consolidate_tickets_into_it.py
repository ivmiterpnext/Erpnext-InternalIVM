import frappe

def execute():
    # Fix IT's self-link item, currently a leftover pointing at "Tickets" from the original clone
    frappe.db.sql("""
        UPDATE `tabWorkspace Sidebar Item`
        SET link_to = 'IT'
        WHERE parent = 'IT' AND link_type = 'Workspace' AND link_to = 'Tickets'
    """)

    # Retire the legacy/duplicate "Tickets" workspace in favor of "IT"
    for doctype, name in (
        ("Desktop Icon", "Tickets"),
        ("Workspace Sidebar", "Tickets"),  # cascades its Workspace Sidebar Item children
        ("Workspace", "Tickets"),          # cascades its Workspace Shortcut children (none currently)
    ):
        if frappe.db.exists(doctype, name):
            frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
