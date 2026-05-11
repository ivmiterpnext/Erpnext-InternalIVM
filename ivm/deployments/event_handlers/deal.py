import frappe
from ivm.deployments.services.provision_from_deal import create_project_from_deal

# Set to True to re-enable automatic Project creation when a CRM Deal is won.
AUTO_CREATE_PROJECT_FROM_DEAL = False


def on_update(doc, method=None):
    """When a CRM Deal status changes to Won, create a deployment Project."""
    if not AUTO_CREATE_PROJECT_FROM_DEAL:
        return

    if doc.status != "Won":
        return

    previous = doc.get_doc_before_save()
    if previous and previous.status == "Won":
        return

    deal_key = doc.get("custom_hubspot_deal") or doc.name
    if frappe.db.exists("Project", {"custom_hubspot_deal_id": deal_key}):
        frappe.logger("deployments").info(
            f"Project already exists for CRM Deal {doc.name}, skipping"
        )
        return

    try:
        project_name = create_project_from_deal(doc.name)
        frappe.msgprint(
            f'Project <a href="/app/project/{project_name}">{project_name}</a> created from deal.',
            title="Deployment Project Created",
            indicator="green",
        )
    except Exception:
        frappe.log_error(
            title=f"Failed to create Project from CRM Deal {doc.name}",
            message=frappe.get_traceback(with_context=True),
        )
