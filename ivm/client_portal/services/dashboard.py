"""
Dashboard summary data for the client portal.
"""

import frappe


def get_dashboard_summary(user: str) -> dict:
	"""
	Aggregate the data needed to render the portal dashboard for a given user.

	Returns a dict of summary values. Add new keys here as more portal
	features get dashboard tiles, rather than scattering per-feature queries
	across www page controllers.
	"""
	contact_name = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact_name:
		return {"pending_quote_count": 0, "active_deployment_count": 0}

	pending_signer_rows = frappe.get_all(
		"Service Quote Signer",
		filters={"contact": contact_name, "status": "Pending"},
		fields=["parent"],
	)
	parent_names = [row.parent for row in pending_signer_rows]

	pending_quote_count = 0
	if parent_names:
		pending_quote_count = frappe.db.count(
			"Service Quote",
			filters={
				"name": ["in", parent_names],
				"status": ["in", ["Sent", "Partially Accepted"]],
			},
		)

	customer_names = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": "Contact",
			"parent": contact_name,
			"link_doctype": "Customer",
		},
		pluck="link_name",
	)

	active_deployment_count = 0
	if customer_names:
		active_deployment_count = frappe.db.count(
			"Project",
			filters={
				"customer": ["in", customer_names],
				"project_type": "Deployment",
				"status": ["!=", "Cancelled"],
			},
		)

	return {
		"pending_quote_count": pending_quote_count,
		"active_deployment_count": active_deployment_count,
	}
