"""
Deployment (Project) data for the client portal.
"""

import frappe


def get_deployments_for_user(user: str) -> list[dict]:
	"""
	Return all Deployment projects visible to the given user's Contact.

	Visibility is Customer-based: resolves every Customer the user's Contact
	is linked to (via the standard Dynamic Link mechanism — a Contact may be
	linked to more than one Customer), then returns every Deployment-type
	Project belonging to any of those Customers.
	"""
	contact_name = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact_name:
		return []

	customer_names = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"parent": contact_name,
			"link_doctype": "Customer",
		},
		pluck="link_name",
	)
	if not customer_names:
		return []

	return frappe.get_all(
		"Project",
		filters={
			"customer": ["in", customer_names],
			"project_type": "Deployment",
		},
		fields=["name", "project_name", "status", "stage"],
		order_by="modified desc",
	)
