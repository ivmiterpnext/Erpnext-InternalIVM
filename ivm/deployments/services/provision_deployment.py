# This file lives with the doctype being affected

import frappe
from frappe.utils import today, add_days

def is_won_deal_status(status):
    status_doc = frappe.get_value(
        "CRM Deal Status", {"deal_status": status},
        ["name", "type"]
    )
    return bool(status_doc and status_doc[1] == "Won")

def generate_deployment(deal):
    # idempotency: store a link field on Opportunity, or check by reference
    if deal.get("ivm_project"):
        return

    project = frappe.get_doc({
        "doctype": "Project",
        "name": f"{deal.customer_name} - {deal.location_name}, ({deal.smartstation_count}, {deal.smartlocker_count}, {deal.smartvault_count}, {deal.smartcenter_count})",
        "project_type": "Deployment",
        "status": "Open",
        "stage": "Waiting Assignment",
        "expected_start_date": today(),
        "expected_end_date": add_days(today(), 56),
        "target_ship_date": add_days(today(), 42),

    })
    project.insert(ignore_permissions=True)
    deal.db_set("ivm_project", project.name, update_modified=False)