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

from ivm.integrations.hubspot.constants import CONTACT_TYPE_ID, HUBSPOT_CONTACT_ID_FIELD
from ivm.integrations.hubspot.sync_utils import SyncLockBusy, save_doc

_LOG = "ivm.deployments.provision_client"


def _link_contact_to_customer(contact_doc: Any, customer_name: str) -> None:
	"""Link a Frappe Contact to a Customer via the Contact's links child table.

	Acquires the same per-contact HubSpot sync lock that _ensure_contacts and
	sync_contact use (when the contact has a HubSpot ID) before saving, because
	this function runs during Won-deal provisioning and can otherwise race
	against those properly-locked paths for a Contact shared across multiple
	deals. If the lock can't be acquired within the timeout, the exception is
	allowed to propagate -- the caller (apply_deal_customer, invoked via
	run_guarded in deal.py::on_update) already absorbs it without blocking the
	rest of the deal sync, so this function must not swallow it locally.

	Uses save_doc's reload-and-retry pattern (not a bare .save()) because this
	Contact may be concurrently modified by the HubSpot contact sync path
	(contact_handler.upsert_contact) for the same record.
	"""
	hubspot_contact_id = contact_doc.get(HUBSPOT_CONTACT_ID_FIELD)
	lock = None
	if hubspot_contact_id:
		lock_key = frappe.cache.make_key(f"hubspot_sync_lock:{CONTACT_TYPE_ID}:{hubspot_contact_id}")
		lock = frappe.cache.lock(lock_key, timeout=1500, blocking_timeout=30)
		if not lock.acquire():
			# Nothing acquired, so nothing to release: raise before the try/finally.
			raise SyncLockBusy(CONTACT_TYPE_ID, hubspot_contact_id)

	try:

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
	finally:
		if lock is not None:
			try:
				lock.release()
			except Exception:
				pass


def get_primary_contact(deal: Any) -> Any | None:
	"""Return the Frappe Contact doc for the deal's primary contact."""
	contacts = deal.get("contacts") or []

	primary_row = next((r for r in contacts if r.is_primary), None)
	if not primary_row and contacts:
		primary_row = contacts[0]

	if not primary_row:
		return None

	return frappe.get_doc("Contact", primary_row.contact)
