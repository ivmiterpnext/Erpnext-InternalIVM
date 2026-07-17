import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification


def after_insert(doc, method=None):
    """Notify Stock Managers when a Material Transfer is created for a Build or Shipping Request."""
    if doc.stock_entry_type != "Material Transfer" or not doc.custom_warehouse_request:
        return

    wr_name = doc.custom_warehouse_request
    request_reason = frappe.db.get_value("Warehouse Request", wr_name, "request_reason")

    if not request_reason:
        return
    if request_reason != "Shipping Request" and not request_reason.startswith("Build"):
        return

    stock_managers = frappe.get_all(
        "Has Role",
        filters={"role": "Stock Manager", "parenttype": "User"},
        pluck="parent",
    )

    if not stock_managers:
        return

    enabled_managers = frappe.get_all(
        "User",
        filters=[
            ["name", "in", stock_managers],
            ["enabled", "=", 1],
            ["name", "!=", frappe.session.user],
        ],
        pluck="name",
    )

    if not enabled_managers:
        return

    notification_doc = {
        "type": "Alert",
        "document_type": "Stock Entry",
        "document_name": doc.name,
        "subject": f"Material Transfer {doc.name} created for {wr_name} — awaiting submission.",
        "from_user": frappe.session.user,
        "email_content": f'<div>A draft Stock Entry <a href="/app/stock-entry/{doc.name}">{doc.name}</a> '
                          f'has been created for Warehouse Request '
                          f'<a href="/app/warehouse-request/{wr_name}">{wr_name}</a> '
                          f'and is awaiting submission.</div>',
    }

    enqueue_create_notification(enabled_managers, notification_doc)


def on_submit(doc, method=None):
    """Notify WR assignees when a Material Transfer is submitted for a Build or Shipping Request."""
    if doc.stock_entry_type != "Material Transfer" or not doc.custom_warehouse_request:
        return

    wr_name = doc.custom_warehouse_request
    request_reason = frappe.db.get_value("Warehouse Request", wr_name, "request_reason")

    if not request_reason:
        return
    if request_reason != "Shipping Request" and not request_reason.startswith("Build"):
        return

    assignees = frappe.get_all(
        "ToDo",
        filters={
            "reference_type": "Warehouse Request",
            "reference_name": wr_name,
            "status": ("not in", ("Cancelled", "Closed")),
        },
        pluck="allocated_to",
    )

    if not assignees:
        return

    notification_doc = {
        "type": "Alert",
        "document_type": "Warehouse Request",
        "document_name": wr_name,
        "subject": f"Material Transfer {doc.name} has been submitted for {wr_name}.",
        "from_user": frappe.session.user,
        "email_content": f'<div>Stock Entry <a href="/app/stock-entry/{doc.name}">{doc.name}</a> '
                          f'has been submitted for Warehouse Request '
                          f'<a href="/app/warehouse-request/{wr_name}">{wr_name}</a>.</div>',
    }

    enqueue_create_notification(assignees, notification_doc)
