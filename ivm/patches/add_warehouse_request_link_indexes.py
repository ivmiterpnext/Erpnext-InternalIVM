import frappe


def execute():
    """Add DB indexes on unindexed Link fields pointing to Warehouse Request.

    Issue.related_warehouse_request (87k+ rows) and Task.custom_warehouse_request
    (57k+ rows) had no index, causing the 1s statement timeout in
    frappe.desk.notifications.get_open_count to intermittently trip on the
    Connections tab's linked-document count query, rendering a literal "?"
    badge for the "Ticket" (Issue) and Task connection groups on Warehouse
    Request.
    """
    frappe.db.add_index("Issue", ["related_warehouse_request"])
    frappe.db.add_index("Task", ["custom_warehouse_request"])
    frappe.clear_cache(doctype="Issue")
    frappe.clear_cache(doctype="Task")
