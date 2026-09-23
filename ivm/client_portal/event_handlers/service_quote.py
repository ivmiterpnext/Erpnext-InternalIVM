"""
Event handlers for Service Quote documents.
"""

import frappe
from frappe.model.document import Document


def on_submit(doc: Document, method: str | None = None) -> None:
	"""
	When a Service Quote is submitted:
	1. If no signers exist, add one row with the contact and Portal Checkbox method.
	2. Ensure portal users exist for all signers.
	3. Set status to "Sent".
	"""
	# If no signers, add one for the primary contact (use db_insert since we're post-save)
	signers_to_process = []
	if not doc.signers:
		signer_doc = frappe.get_doc(
			{
				"doctype": "Service Quote Signer",
				"parent": doc.name,
				"parenttype": "Service Quote",
				"parentfield": "signers",
				"contact": doc.contact,
				"signature_method": "Portal Checkbox",
				"status": "Pending",
			}
		)
		signer_doc.db_insert()
		signers_to_process = [signer_doc]
	else:
		signers_to_process = doc.signers

	# Ensure portal users exist for all signers
	for signer in signers_to_process:
		frappe.call(
			"ivm.client_portal.services.provisioning.ensure_portal_user",
			contact=signer.contact,
			async_=False,
		)

	# Set status to Sent
	frappe.db.set_value("Service Quote", doc.name, "status", "Sent")
