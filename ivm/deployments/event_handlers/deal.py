"""
Event handlers for CRM Deal documents.
"""

import frappe
from frappe.model.document import Document

from ivm.deployments.services.provision_project_from_deal import create_projects_from_deal
from ivm.integrations.hubspot.customer_resolution import (
	apply_deal_customer,
	resolve_deal_customer,
	run_guarded,
)


def on_update(doc: Document, method: str | None = None) -> None:
	"""When a CRM Deal status changes to Won, resolve its Customer (applying it to the deal and
	its blank Projects), then create one deployment Project per Deployment Location.

	Nothing is created in iCorp here. If no Customer resolves, the Projects are created with a
	blank Customer, and the deployer sets it on each Project. Customer-resolution failures are
	logged and never block the save.
	"""
	if doc.status != "Won" or not doc.has_value_changed("status"):
		return

	if not frappe.db.exists("Deployment Location", {"crm_deal": doc.name}):
		frappe.log_error(
			title=f"CRM Deal {doc.name} marked Won with no Deployment Locations",
			message=(
				f"Deal '{doc.name}' was marked Won but has no Deployment Locations linked. "
				"Customer resolution and field sync proceeded; no deployments were created."
			),
		)
		frappe.msgprint(
			"This deal has no Deployment Locations linked — no deployments were created. "
			"Link a Deployment Location to generate deployments.",
			title="No Deployment Locations",
			indicator="orange",
			alert=True,
		)

	# Resolve the Customer before project creation so custom_customer is available.
	# Never raises: a failure here must not block the save or the rest of on_update.
	customer_name = None
	try:
		customer_name = resolve_deal_customer(doc)
	except Exception:
		frappe.log_error(
			title=f"Customer resolution failed for CRM Deal {doc.name}",
			message=frappe.get_traceback(with_context=True),
		)
	if customer_name and run_guarded(
		f"Customer propagation failed for CRM Deal {doc.name}",
		apply_deal_customer,
		doc.name,
		customer_name,
	):
		doc.reload()

	try:
		created = create_projects_from_deal(doc.name)

		if created:
			links = ", ".join(f'<a href="/app/project/{n}">{n}</a>' for n in created)
			frappe.msgprint(
				f"Created {len(created)} deployment(s): {links}",
				title="Deployments Created",
				indicator="green",
			)

	except Exception:
		frappe.log_error(
			title=f"Failed to create Deployments from CRM Deal {doc.name}",
			message=frappe.get_traceback(with_context=True),
		)


def ensure_deployment_location_for_test(doc: Document, method: str | None = None) -> None:
	"""Create a stub Deployment Location so crm's Won-status test fixtures
	survive ivm's on_update validation.

	Registered as a ``before_test_insert`` doc_event — only ever called by
	``frappe.tests.utils.generators._try_create()``, never during real
	document inserts/saves (confirmed: no production code path invokes
	``run_method("before_test_insert")``).
	"""
	if doc.status != "Won":
		return
	if frappe.db.exists("Deployment Location", {"crm_deal": doc.name}):
		return
	frappe.get_doc(
		{
			"doctype": "Deployment Location",
			"crm_deal": doc.name,
			"location_name": f"Test Location for {doc.name}",
		}
	).insert(ignore_permissions=True, ignore_links=True)
