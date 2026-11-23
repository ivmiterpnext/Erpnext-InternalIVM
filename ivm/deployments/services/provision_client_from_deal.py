"""
Contact helpers for CRM Deals, shared by Customer resolution
(ivm.integrations.hubspot.customer_resolution) and the client portal.

Nothing here talks to iCorp. iCorp contacts and clients are created only on
explicit user action from the Customer form (see
ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link
.create_icorp_client_for_customer, which uses ivm.integrations.icorp.provisioning).
"""

from __future__ import annotations

from typing import Any

import frappe

from ivm.integrations.hubspot.sync_utils import save_doc

_LOG = "ivm.deployments.provision_client"


def _link_contact_to_customer(contact_doc: Any, customer_name: str) -> None:
	"""Link a Frappe Contact to a Customer via the Contact's links child table.

	Uses save_doc's reload-and-retry pattern (not a bare .save()) because this
	Contact may be concurrently modified by the HubSpot contact sync path
	(contact_handler.upsert_contact) for the same record — without a retry,
	that race surfaces as an unhandled TimestampMismatchError.
	"""

	def _apply_link(doc: Any) -> None:
		for link in doc.get("links") or []:
			if link.link_doctype == "Customer" and link.link_name == customer_name:
				return
		doc.append("links", {"link_doctype": "Customer", "link_name": customer_name})

	for link in contact_doc.get("links") or []:
		if link.link_doctype == "Customer" and link.link_name == customer_name:
			return

	_apply_link(contact_doc)
	save_doc(contact_doc, "contact-customer-link", mutate=_apply_link)

	frappe.logger(_LOG).info(f"Linked Contact '{contact_doc.name}' to Customer '{customer_name}'")


def get_primary_contact(deal: Any) -> Any | None:
	"""Return the Frappe Contact doc for the deal's primary contact."""
	contacts = deal.get("contacts") or []

	primary_row = next((r for r in contacts if r.is_primary), None)
	if not primary_row and contacts:
		primary_row = contacts[0]

	if not primary_row:
		return None

	return frappe.get_doc("Contact", primary_row.contact)
