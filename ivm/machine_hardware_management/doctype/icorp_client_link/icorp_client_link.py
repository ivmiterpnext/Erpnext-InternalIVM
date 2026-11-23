# Copyright (c) 2026, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from ivm.deployments.services.deployment_clients import require_desk_customer_access
from ivm.integrations.icorp.api import icorp_api_get
from ivm.integrations.icorp.provisioning import (
	build_contact_payload,
	create_icorp_client_with_error,
	create_icorp_contact_with_error,
	get_contact_phone,
	log_icorp_error,
)


def _refresh_icorp_client_ids_cache(customer: str | None, exclude_name: str | None = None) -> None:
	"""Recompute Customer.icorp_client_ids (comma-joined, active clients only) for one
	customer. Called whenever an iCorp Client Link's customer assignment changes.

	exclude_name: a Link being deleted (on_trash runs before its row is removed), so it
	must be left out of the recomputed list."""
	if not customer or not frappe.db.exists("Customer", customer):
		return
	filters = {"customer": customer, "is_active": 1}
	if exclude_name:
		filters["name"] = ["!=", exclude_name]
	ids = frappe.get_all(
		"iCorp Client Link",
		filters=filters,
		pluck="name",
		order_by="name asc",
	)
	frappe.db.set_value("Customer", customer, "icorp_client_ids", ", ".join(ids))


class iCorpClientLink(Document):
	def before_save(self):
		self.display_label = f"({self.icorp_client_id}) {self.client_name or ''}".strip()

	def on_update(self):
		_refresh_icorp_client_ids_cache(self.customer)
		before = self.get_doc_before_save()
		if before and before.customer and before.customer != self.customer:
			_refresh_icorp_client_ids_cache(before.customer)

	def on_trash(self):
		if self.customer:
			_refresh_icorp_client_ids_cache(self.customer, exclude_name=self.name)


@frappe.whitelist()
def icorp_client_query(doctype, txt, searchfield, start, page_len, filters):
	"""set_query source for Project.client_id (and similar fields): clients belonging to a
	specific Customer, matched against either the client id or its name."""
	require_desk_customer_access()
	customer = (filters or {}).get("customer")
	conditions = []
	values = {"txt": f"%{txt}%", "start": start, "page_len": page_len}

	if customer:
		conditions.append("customer = %(customer)s")
		values["customer"] = customer

	conditions.append("(icorp_client_id like %(txt)s or client_name like %(txt)s)")

	return frappe.db.sql(
		f"""
		select name, display_label
		from `tabiCorp Client Link`
		where {" and ".join(conditions)}
		order by is_active desc, client_name asc
		limit %(page_len)s offset %(start)s
		""",
		values,
	)


_LIVE_ASSIGNMENT_ROLES = ("System Manager", "Projects Manager")


def _check_live_assignment_permission() -> None:
	frappe.only_for(_LIVE_ASSIGNMENT_ROLES, message=True)


def _fetch_icorp_client(client_id: str) -> dict:
	if not str(client_id).strip().isdigit():
		frappe.throw(f"'{client_id}' is not a valid numeric iCorp Client ID.")
	try:
		response = icorp_api_get(f"Client/GetById?Id={client_id}")
	except Exception as e:
		if "'status': 404" in str(e):
			frappe.throw(f"No iCorp client found with ID {client_id}.")
		raise
	data = response.get("data") if isinstance(response, dict) else None
	if not data:
		frappe.throw(f"No iCorp client found with ID {client_id}.")
	return data


@frappe.whitelist()
def lookup_icorp_client(client_id: str, customer: str) -> dict:
	"""Read-only: fetch client_id from iCorp and report its current Frappe state
	relative to `customer`, without writing anything."""
	_check_live_assignment_permission()
	client_id = str(client_id).strip()
	data = _fetch_icorp_client(client_id)

	existing = frappe.db.get_value(
		"iCorp Client Link", client_id, ["customer", "is_active", "parent_client"], as_dict=True
	)
	current_customer = existing.customer if existing else None

	parent_id = data.get("partner_client_id")
	parent_label = None
	parent_customer = None
	if parent_id:
		parent_label = frappe.db.get_value("iCorp Client Link", str(parent_id), "display_label")
		parent_customer = frappe.db.get_value("iCorp Client Link", str(parent_id), "customer")

	if current_customer == customer:
		status = "already_on_this_customer"
	elif current_customer:
		status = "assigned_elsewhere"
	else:
		status = "unassigned"

	return {
		"client_id": client_id,
		"client_name": data.get("name") or "",
		"is_active": bool(data.get("is_active")),
		"sv_location_count_active": data.get("sv_location_count_active") or 0,
		"sv_machine_count_active": data.get("sv_machine_count_active") or 0,
		"parent_client_id": str(parent_id) if parent_id else None,
		"parent_client_label": parent_label,
		"parent_customer": parent_customer,
		"status": status,
		"current_customer": current_customer,
	}


def _upsert_icorp_client_identity(client_id: str, data: dict) -> None:
	"""Create or update the identity fields of one iCorp Client Link from a fresh
	iCorp API record, exactly mirroring sync_icorp_client_links()'s per-record shape,
	without touching customer/assignment_source/review fields."""
	display_label = f"({client_id}) {data.get('name') or ''}".strip()
	values = {
		"client_name": data.get("name") or "",
		"display_label": display_label,
		"is_active": 1 if data.get("is_active") else 0,
		"is_partner_client": 1 if data.get("is_partner_client") else 0,
		"sv_location_count_active": data.get("sv_location_count_active") or 0,
		"sv_machine_count_active": data.get("sv_machine_count_active") or 0,
	}
	if frappe.db.exists("iCorp Client Link", client_id):
		frappe.db.set_value("iCorp Client Link", client_id, values)
	else:
		frappe.get_doc({"doctype": "iCorp Client Link", "icorp_client_id": client_id, **values}).insert(
			ignore_permissions=True
		)


def _ensure_parent_client_synced(data: dict) -> None:
	"""If this client's iCorp parent isn't in Frappe yet, fetch and create it too, then
	link parent_client -- otherwise managed/partner derivation can't work for a brand
	new partner-managed client."""
	parent_id = data.get("partner_client_id")
	if not parent_id:
		return
	parent_id = str(parent_id)
	if not frappe.db.exists("iCorp Client Link", parent_id):
		parent_data = _fetch_icorp_client(parent_id)
		_upsert_icorp_client_identity(parent_id, parent_data)
	client_id = str(data["id"])
	frappe.db.set_value("iCorp Client Link", client_id, "parent_client", parent_id)


@frappe.whitelist()
def add_icorp_client_to_customer(client_id: str, customer: str) -> dict:
	"""Attach an iCorp client to `customer`. Refuses if the client is already assigned
	to a DIFFERENT Customer -- it must be removed from that Customer first."""
	_check_live_assignment_permission()
	if not frappe.db.exists("Customer", customer):
		frappe.throw(f"Customer '{customer}' does not exist.")

	client_id = str(client_id).strip()
	data = _fetch_icorp_client(client_id)

	current_customer = frappe.db.get_value("iCorp Client Link", client_id, "customer")
	if current_customer and current_customer != customer:
		frappe.throw(
			f"iCorp Client {client_id} is already assigned to Customer '{current_customer}'. "
			"Remove it from that Customer first."
		)

	_upsert_icorp_client_identity(client_id, data)
	_ensure_parent_client_synced(data)

	doc = frappe.get_doc("iCorp Client Link", client_id)
	doc.customer = customer
	doc.assignment_source = "Customer form"
	doc.flags.live_assignment = True
	doc.save(ignore_permissions=True)

	return {"client_id": client_id, "customer": customer}


@frappe.whitelist()
def remove_icorp_client_from_customer(client_id: str, customer: str) -> dict:
	"""Detach an iCorp client from `customer`. Refuses if the client is not currently
	assigned to `customer` (e.g. a stale page, or someone else already removed it)."""
	_check_live_assignment_permission()
	client_id = str(client_id).strip()

	current_customer = frappe.db.get_value("iCorp Client Link", client_id, "customer")
	if current_customer != customer:
		frappe.throw(
			f"iCorp Client {client_id} is not currently assigned to Customer '{customer}' "
			f"(currently: {current_customer or 'unassigned'})."
		)

	doc = frappe.get_doc("iCorp Client Link", client_id)
	doc.customer = None
	doc.assignment_source = "Customer form"
	doc.flags.live_assignment = True
	doc.save(ignore_permissions=True)

	return {"client_id": client_id, "removed_from": customer}


@frappe.whitelist()
def get_customer_contacts(customer: str) -> list[dict]:
	"""Every Contact linked to `customer` via Dynamic Link, with what iCorp would receive
	for it: display name, primary email and primary phone (empty string when missing).
	Used by the Customer form's "Create new in iCorp" dialog."""
	_check_live_assignment_permission()
	if not customer or not frappe.db.exists("Customer", customer):
		return []

	linked_names = set(
		frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
			pluck="parent",
		)
	)
	# Dynamic Link rows can outlive their parent Contact (orphans; 3,277 on dev.local), so only
	# keep names that still exist as a Contact before loading any doc.
	contact_names = (
		frappe.get_all("Contact", filters={"name": ["in", list(linked_names)]}, pluck="name")
		if linked_names
		else []
	)

	out = []
	for name in sorted(contact_names):
		contact_doc = frappe.get_doc("Contact", name)
		payload = build_contact_payload(contact_doc)
		display_name = " ".join(
			part for part in (contact_doc.first_name, contact_doc.last_name) if part
		).strip()
		out.append(
			{
				"name": name,
				"display_name": display_name or name,
				"email": payload["email_address"] or contact_doc.get("email_id") or "",
				"phone": payload["phone1"],
			}
		)
	out.sort(key=lambda c: c["display_name"].lower())
	return out


@frappe.whitelist()
def create_icorp_client_for_customer(
	customer: str, client_name: str, contact: str, partner_client_id: str | None = None
) -> dict:
	"""Create a NEW client in iCorp for `customer` and link it to this Customer.

	Creates the iCorp contact from the Frappe Contact, then the iCorp client, then the
	iCorp Client Link (assignment_source "Customer form"). Every failure is thrown to
	the user. If the contact is created but the client is not, the message names the
	iCorp contact id so nothing is silently left behind.

	partner_client_id: optional existing iCorp Client Link id that manages this client
	(sent as the client's iCorp parent, and stored as parent_client).
	"""
	_check_live_assignment_permission()

	if not frappe.db.exists("Customer", customer):
		frappe.throw(f"Customer '{customer}' does not exist.")
	if frappe.db.get_value("Customer", customer, "disabled"):
		frappe.throw(f"Customer '{customer}' is disabled.")

	client_name = (client_name or "").strip()
	if not client_name:
		frappe.throw("Client name is required.")

	if not contact or not frappe.db.exists("Contact", contact):
		frappe.throw("Select the primary Contact for this client.")
	if not frappe.db.exists(
		"Dynamic Link",
		{"parenttype": "Contact", "parent": contact, "link_doctype": "Customer", "link_name": customer},
	):
		frappe.throw(
			f"Contact '{contact}' is not linked to Customer '{customer}'. Link the Contact to the Customer first."
		)

	partner_client_id = str(partner_client_id).strip() if partner_client_id else ""
	if partner_client_id and not frappe.db.exists("iCorp Client Link", partner_client_id):
		frappe.throw(f"Managing partner iCorp client '{partner_client_id}' does not exist.")

	contact_doc = frappe.get_doc("Contact", contact)
	if not get_contact_phone(contact_doc):
		frappe.throw(
			f"iCorp requires at least one phone number on the contact. Add a phone number to {contact} first."
		)

	icorp_contact_id, contact_error = create_icorp_contact_with_error(contact_doc)
	if icorp_contact_id is None:
		frappe.throw(
			f"iCorp rejected the contact '{contact}', so no client was created. "
			f"iCorp said: {contact_error}. "
			"See the Error Log entry 'iCorp: failed to create contact' for details."
		)

	icorp_client_id, client_error = create_icorp_client_with_error(
		client_name,
		icorp_contact_id,
		partner_client_id=int(partner_client_id) if partner_client_id else None,
	)
	if icorp_client_id is None:
		frappe.throw(
			f"The iCorp contact (ID {icorp_contact_id}) was created, but the iCorp client "
			f"'{client_name}' was not. iCorp said: {client_error}. Nothing was linked to Customer "
			f"'{customer}'. The contact still exists in iCorp. "
			"See the Error Log entry 'iCorp: failed to create client' for details."
		)

	client_id = str(icorp_client_id)
	try:
		_upsert_icorp_client_identity(client_id, {"name": client_name, "is_active": True})
		doc = frappe.get_doc("iCorp Client Link", client_id)
		doc.customer = customer
		doc.assignment_source = "Customer form"
		doc.parent_client = partner_client_id or None
		doc.flags.live_assignment = True
		doc.save(ignore_permissions=True)
	except Exception:
		log_icorp_error(
			f"iCorp: client {client_id} created but Frappe link failed",
			frappe.get_traceback(with_context=True),
		)
		frappe.throw(
			f"iCorp client {client_id} ('{client_name}') was created in iCorp (contact ID "
			f"{icorp_contact_id}), but linking it to Customer '{customer}' in Frappe failed. "
			"See the Error Log for details."
		)

	return {"client_id": client_id, "customer": customer}


@frappe.whitelist()
def get_child_clients(parent_client: str) -> list[dict]:
	"""Every iCorp client whose iCorp parent is this one — shown on the parent's form so a
	partner's siblings (e.g. Zones' managed clients) are visible without searching."""
	frappe.only_for("System Manager")
	return frappe.get_all(
		"iCorp Client Link",
		filters={"parent_client": parent_client},
		fields=[
			"name",
			"display_label",
			"is_active",
			"customer",
			"sv_machine_count_active",
		],
		order_by="is_active desc, client_name asc",
	)
