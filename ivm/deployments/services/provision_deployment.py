# This file lives with the doctype being affected

import frappe
from frappe.utils import today

CLOSED_WON = "Closed Won"  # adjust to your actual value

def ensure_project_for_closed_opportunity(opp):
    if opp.status != CLOSED_WON:
        return

    # idempotency: store a link field on Opportunity, or check by reference
    if opp.get("ivm_project"):
        return

    project = frappe.get_doc({
        "doctype": "Project",
        "project_name": f"{opp.customer_name} - Deployment",
        "expected_start_date": today(),
        # set your date fields here
    })
    project.insert(ignore_permissions=True)

    opp.db_set("ivm_project", project.name, update_modified=False)