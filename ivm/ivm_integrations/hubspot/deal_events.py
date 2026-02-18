import frappe
from frappe import _


def on_update(doc, method):
	"""Create a Deployment Project when a CRM Deal moves to a Won status.

	Registered via ``doc_events`` in hooks.py so it fires on every
	CRM Deal save — whether triggered by a HubSpot webhook, manual
	UI change, or API call.

	Idempotent: skips if a Project already exists linked to this deal.
	"""
	status_type = frappe.db.get_value("CRM Deal Status", doc.status, "type")
	if status_type != "Won":
		return

	if frappe.db.exists("Project", {"crm_deal": doc.name}):
		return

	project = frappe.new_doc("Project")
	project.project_name = doc.deal_name or _("Deployment - {0}").format(doc.name)
	project.project_type = "Deployment"
	project.crm_deal = doc.name
	project.expected_end_date = doc.expected_closure_date
	project.insert(ignore_permissions=True)

	frappe.logger().info(
		f"Created Deployment Project '{project.name}' for CRM Deal '{doc.name}'"
	)
