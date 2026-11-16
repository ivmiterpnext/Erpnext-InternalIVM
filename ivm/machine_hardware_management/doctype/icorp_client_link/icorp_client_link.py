# Copyright (c) 2026, Dev and contributors
# For license information, please see license.txt

import os

import frappe
from frappe.model.document import Document

from ivm.customer_consolidation import decisions, merge_analysis
from ivm.customer_consolidation.apply import execute_merges
from ivm.customer_consolidation.decisions import compute_review_status
from ivm.deployments.services.deployment_clients import require_desk_customer_access
from ivm.integrations.icorp.api import icorp_api_get
from ivm.integrations.icorp.provisioning import (
	build_contact_payload,
	create_icorp_client_with_error,
	create_icorp_contact_with_error,
	get_contact_phone,
	log_icorp_error,
)


class iCorpClientLink(Document):
	def before_save(self):
		self.display_label = f"({self.icorp_client_id}) {self.client_name or ''}".strip()

	def onload(self):
		self.set_onload("is_review_site", _is_review_site())

	def validate(self):
		rows = self.get("related_customers") or []
		survivors = [r for r in rows if r.role == "This client's Customer"]
		if len(survivors) > 1:
			frappe.throw(
				'Only one row in Related Customers can be marked "This client\'s Customer" '
				f"(found {len(survivors)})."
			)
		for r in rows:
			if r.role == "Duplicate - merge in" and not survivors:
				frappe.throw(
					'Mark one row "This client\'s Customer" before marking others "Duplicate - merge in".'
				)

		if survivors:
			survivor_customer = survivors[0].customer
			if self.customer and self.customer != survivor_customer:
				frappe.throw(
					f"Related Customers marks '{survivor_customer}' as this client's Customer, "
					f"but Customer is set to '{self.customer}'. They must match."
				)
			self.customer = survivor_customer
			self.assignment_source = "Manual decision"

		if not _is_review_site() and not self.flags.live_assignment:
			before = self.get_doc_before_save()
			if before:
				before_rows = [(r.customer, r.role) for r in (before.get("related_customers") or [])]
				after_rows = [(r.customer, r.role) for r in rows]
				if before.customer != self.customer or before_rows != after_rows:
					frappe.throw(
						"Decisions are made on the review site and deployed via the repo CSVs; "
						"this site can't record new ones."
					)

		existing_customers = set(frappe.get_all("Customer", pluck="name"))
		row_dicts = [{"customer": r.customer, "role": r.role} for r in rows]
		self.review_status = compute_review_status(
			self.customer, self.proposed_customer, row_dicts, existing_customers
		)

	def on_update(self):
		if not _is_review_site():
			return
		if self.flags.live_assignment:
			# Live operational assignments (Customer form add/remove/create) are not review
			# decisions and must never be written back to the repo CSVs (e.g. a dev-only iCorp
			# id would make prod's apply_on_migrate fail).
			return
		client_id = self.icorp_client_id
		rows = [{"customer": r.customer, "role": r.role} for r in (self.get("related_customers") or [])]
		customer = self.customer
		if not customer and not rows:
			# A brand-new/freshly-synced Link (e.g. sync_icorp_client_links()'s bulk .insert() of
			# ~1,390 clients, which runs after any restore since this doctype doesn't exist in
			# prod's own database dump) has no actual decision recorded yet. _write_decisions_for_client
			# writes icorp_client_assignments.csv/customer_distinct_pairs.csv unconditionally (not
			# append), so scheduling a write-back of blank state for every one of those ~1,390 clients
			# would silently overwrite nearly every previously-reviewed row in both files down to just
			# their header. Only persist once there's an actual decision (a customer set, or at least
			# one related_customers row).
			return
		frappe.db.after_commit.add(lambda: _write_decisions_for_client(client_id, customer, rows))


def _write_decisions_for_client(client_id: str, customer: str, rows: list[dict]) -> None:
	"""Write this client's current decision state into the three repo CSVs: who it's assigned
	to, which Customers it wants merged (one marked "This client's Customer", others
	"Duplicate - merge in"), and which candidate Customers it has confirmed are different
	companies ("Different company"). Called after a Desk save/bulk-action commits, on the
	review site only."""
	from ivm.customer_consolidation import decisions

	anchor = ""
	for row in rows:
		if row.get("role") == "This client's Customer":
			anchor = row.get("customer") or ""
			break
	if not anchor:
		anchor = customer or ""

	assignment_rows = (
		decisions._read_csv_rows(decisions.CLIENT_ASSIGNMENTS_PATH)
		if os.path.exists(decisions.CLIENT_ASSIGNMENTS_PATH)
		else []
	)
	assignment_rows = decisions.upsert_client_assignment(
		assignment_rows, client_id, customer or "", "Manual decision"
	)
	decisions._write_csv(
		decisions.CLIENT_ASSIGNMENTS_PATH, ["client_id", "customer", "evidence"], assignment_rows
	)

	existing_customers = set(frappe.get_all("Customer", pluck="name"))
	desired_pairs = [
		(row["customer"], anchor)
		for row in rows
		if row.get("role") == "Duplicate - merge in" and row.get("customer") and row["customer"] != anchor
	]
	if desired_pairs:
		merge_rows = decisions.load_customer_merges()
		try:
			merge_rows = decisions.upsert_client_merges(
				merge_rows, client_id, desired_pairs, existing_customers
			)
			decisions._write_csv(
				decisions.CUSTOMER_MERGES_PATH,
				[
					"merge_from",
					"merge_into",
					"evidence",
					"merge_considerations",
					"field_resolutions",
					"source_client_id",
				],
				merge_rows,
			)
		except ValueError as e:
			frappe.log_error(
				title=f"Customer consolidation: merge decision conflict (client {client_id})",
				message=str(e),
			)

	dismissed = [
		row["customer"] for row in rows if row.get("role") == "Different company" and row.get("customer")
	]
	pair_rows = (
		decisions._read_csv_rows(decisions.CUSTOMER_DISTINCT_PAIRS_PATH)
		if os.path.exists(decisions.CUSTOMER_DISTINCT_PAIRS_PATH)
		else []
	)
	pair_rows = decisions.upsert_distinct_pairs(pair_rows, client_id, anchor, dismissed)
	decisions._write_csv(
		decisions.CUSTOMER_DISTINCT_PAIRS_PATH, ["customer_a", "customer_b", "client_id", "note"], pair_rows
	)


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


_SOURCE_BY_MATCH_STATUS = {
	"confirmed": "Confirmed match",
	"existing_field_only": "Confirmed match",
	"project_only": "Project evidence",
	"name_exact_only": "Name match",
	"name_fuzzy_only": "Name match",
}


def _is_review_site() -> bool:
	return bool(frappe.conf.get("customer_consolidation_review_site"))


@frappe.whitelist()
def is_review_site() -> bool:
	return _is_review_site()


def _as_list(names) -> list[str]:
	if isinstance(names, str):
		return frappe.parse_json(names)
	return names or []


@frappe.whitelist()
def bulk_accept_proposal(names) -> dict:
	"""For each selected iCorp Client Link whose review_status is "Ready to accept", set
	customer = proposed_customer. Everything else is skipped (not an error) — "Ready to accept"
	already means there's exactly one usable candidate and nothing else open."""
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are made on the review site only.")
	accepted, skipped = [], []

	for name in _as_list(names):
		doc = frappe.get_doc("iCorp Client Link", name)
		if doc.review_status != "Ready to accept" or not doc.proposed_customer:
			skipped.append(name)
			continue
		doc.customer = doc.proposed_customer
		doc.assignment_source = _SOURCE_BY_MATCH_STATUS.get(doc.match_status, "Confirmed match")
		doc.save(ignore_permissions=True)
		accepted.append(name)

	frappe.db.commit()
	return {"accepted": accepted, "skipped": skipped}


@frappe.whitelist()
def bulk_assign_customer(names, customer: str) -> dict:
	"""Manually assign the given Customer to every selected iCorp Client Link, overwriting
	whatever was there before — this is always treated as a deliberate human decision."""
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are made on the review site only.")
	if not frappe.db.exists("Customer", customer):
		frappe.throw(f"Customer '{customer}' does not exist")

	assigned = []
	for name in _as_list(names):
		frappe.db.set_value(
			"iCorp Client Link", name, {"customer": customer, "assignment_source": "Manual decision"}
		)
		_write_decisions_for_client(name, customer, [])
		assigned.append(name)

	frappe.db.commit()
	return {"assigned": assigned}


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
def export_decisions() -> dict:
	"""Write every iCorp Client Link with a customer set to decisions/icorp_client_assignments.csv
	in the repo, overwriting the file with the full current picture (not appended) so re-exporting
	after further review always produces a complete, consistent file. This is the bridge between
	review done in Desk and the file-based decision record every environment reads from."""
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are made on the review site only.")
	import csv

	from ivm.customer_consolidation.decisions import CLIENT_ASSIGNMENTS_PATH

	rows = frappe.get_all(
		"iCorp Client Link",
		filters={"customer": ["!=", ""]},
		fields=["icorp_client_id", "customer", "assignment_source", "match_evidence"],
		order_by="icorp_client_id",
	)

	with open(CLIENT_ASSIGNMENTS_PATH, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["client_id", "customer", "evidence"])
		for row in rows:
			evidence = f"[{row.assignment_source or 'Manual decision'}] {row.match_evidence or ''}".strip()
			writer.writerow([row.icorp_client_id, row.customer, evidence])

	return {"path": CLIENT_ASSIGNMENTS_PATH, "rows_written": len(rows)}


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
			"match_status",
			"proposed_customer",
			"sv_machine_count_active",
		],
		order_by="is_active desc, client_name asc",
	)


@frappe.whitelist()
def preview_pending_decisions() -> dict:
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are reviewed and executed on the review site only.")
	from ivm.customer_consolidation.apply import run_apply_decisions

	return run_apply_decisions(execute=False)


@frappe.whitelist()
def execute_pending_decisions() -> str:
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are reviewed and executed on the review site only.")

	job = frappe.enqueue(
		"ivm.customer_consolidation.apply.run_apply_decisions",
		queue="long",
		timeout=1800,
		execute=True,
		now=False,
	)
	return job.id


@frappe.whitelist()
def get_merge_conflicts() -> list[dict]:
	"""Every merge currently blocked by an unresolved field conflict, grouped by survivor
	(merge_into), with the value each side holds for each conflicting field — so the Desk UI
	can offer a dropdown per field instead of requiring field_resolutions to be hand-typed into
	the CSV."""
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are reviewed and executed on the review site only.")

	blocked = [r for r in execute_merges(dry_run=True) if r.get("status") == "blocked"]
	if not blocked:
		return []

	meta = frappe.get_meta("Customer")
	by_survivor: dict[str, dict] = {}

	for row in blocked:
		merge_into = row["merge_into"]
		survivor_entry = by_survivor.setdefault(
			merge_into, {"merge_into": merge_into, "merges": [], "_fields": {}}
		)
		survivor_entry["merges"].append(row["merge_from"])

		for fieldname in row.get("unresolved_field_conflicts", []):
			# unresolved_field_conflicts entries look like "fieldname: 'from_value' vs 'into_value'"
			# from merge_analysis.diff_customer_values — but we only need the fieldname here,
			# values are re-fetched fresh below so they can't go stale between calls.
			plain_fieldname = fieldname.split(":", 1)[0].strip()
			field_entry = survivor_entry["_fields"].setdefault(
				plain_fieldname, {"fieldname": plain_fieldname, "conflicting_merges": []}
			)
			field_entry["conflicting_merges"].append(row["merge_from"])

	results = []
	for merge_into, entry in by_survivor.items():
		fields_out = []
		for plain_fieldname, field_entry in entry["_fields"].items():
			df = meta.get_field(plain_fieldname)
			label = df.label if df else plain_fieldname
			fieldtype = df.fieldtype if df else "Data"

			options = []
			seen_values = set()
			survivor_value = merge_analysis.get_customer_values(merge_into, [plain_fieldname]).get(
				plain_fieldname
			)
			if survivor_value not in (None, ""):
				options.append({"customer": merge_into, "value": survivor_value})
				seen_values.add(survivor_value)

			for merge_from in field_entry["conflicting_merges"]:
				value = merge_analysis.get_customer_values(merge_from, [plain_fieldname]).get(plain_fieldname)
				if value not in (None, "") and value not in seen_values:
					options.append({"customer": merge_from, "value": value})
					seen_values.add(value)

			fields_out.append(
				{
					"fieldname": plain_fieldname,
					"label": label,
					"fieldtype": fieldtype,
					"options": options,
					"conflicting_merges": field_entry["conflicting_merges"],
				}
			)

		results.append({"merge_into": merge_into, "merges": entry["merges"], "fields": fields_out})

	return results


@frappe.whitelist()
def save_merge_resolutions(resolutions) -> dict:
	"""resolutions: {merge_into: {fieldname: {"value": str, "custom": bool}}}. Validates each
	choice against the survivor's CURRENT conflicts (re-checked fresh, not trusted from the
	client), then writes it to every pending customer_merges.csv row that has that field as a
	conflict for that survivor."""
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are reviewed and executed on the review site only.")

	if isinstance(resolutions, str):
		resolutions = frappe.parse_json(resolutions)

	conflicts = get_merge_conflicts()
	conflicts_by_survivor = {c["merge_into"]: c for c in conflicts}

	existing_customers = set(frappe.get_all("Customer", pluck="name"))
	merge_rows = decisions.load_customer_merges()
	updated_rows = 0

	for merge_into, field_choices in resolutions.items():
		survivor_conflicts = conflicts_by_survivor.get(merge_into)
		if not survivor_conflicts:
			frappe.throw(f"'{merge_into}' has no pending merge conflicts to resolve.")
		fields_by_name = {f["fieldname"]: f for f in survivor_conflicts["fields"]}

		for fieldname, choice in field_choices.items():
			field_conflict = fields_by_name.get(fieldname)
			if not field_conflict:
				frappe.throw(f"'{fieldname}' is not a current conflict for '{merge_into}'.")

			value = choice.get("value")
			is_custom = bool(choice.get("custom"))

			if not is_custom:
				offered_values = {o["value"] for o in field_conflict["options"]}
				if value not in offered_values:
					frappe.throw(f"'{value}' was not one of the offered values for '{fieldname}'.")
			else:
				df = frappe.get_meta("Customer").get_field(fieldname)
				fieldtype = df.fieldtype if df else "Data"
				if fieldtype == "Link" and df.options:
					if not frappe.db.exists(df.options, value):
						frappe.throw(f"'{value}' is not a valid {df.options} for '{fieldname}'.")
				elif fieldtype in ("Int", "Float", "Currency", "Percent"):
					try:
						float(value)
					except (TypeError, ValueError):
						frappe.throw(f"'{value}' is not a valid number for '{fieldname}'.")
				elif fieldtype == "Select" and df and df.options:
					valid_options = [o.strip() for o in df.options.split("\n") if o.strip()]
					if value not in valid_options:
						frappe.throw(f"'{value}' is not a valid option for '{fieldname}'.")
				elif value in (None, ""):
					frappe.throw(f"A value is required for '{fieldname}'.")

			for merge_from in field_conflict["conflicting_merges"]:
				merge_rows = decisions.set_field_resolutions(
					merge_rows, merge_from, {fieldname: value}, existing_customers
				)
				updated_rows += 1

	decisions._write_csv(
		decisions.CUSTOMER_MERGES_PATH,
		[
			"merge_from",
			"merge_into",
			"evidence",
			"merge_considerations",
			"field_resolutions",
			"source_client_id",
		],
		merge_rows,
	)

	return {"updated_rows": updated_rows}


@frappe.whitelist()
def create_customer_for_client(
	docname: str, customer_name: str, customer_type: str, customer_group: str, territory: str
) -> str:
	"""Create a brand-new Customer for an iCorp Client Link that doesn't match any existing one,
	assign it to this Link, and record the creation in customers_to_create.csv so the same
	Customer is reproduced on every other environment (a prod deploy, or a dev restored from a
	fresh prod backup) rather than only existing locally."""
	frappe.only_for("System Manager")
	if not _is_review_site():
		frappe.throw("Decisions are made on the review site only.")

	if frappe.db.exists("Customer", customer_name):
		frappe.throw(f"Customer '{customer_name}' already exists.")

	doc = frappe.get_doc("iCorp Client Link", docname)
	if doc.customer:
		frappe.throw(f"This client is already assigned to '{doc.customer}'.")

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": customer_type,
			"customer_group": customer_group,
			"territory": territory,
		}
	).insert(ignore_permissions=True)

	doc.customer = customer.name
	doc.assignment_source = "Manual decision"
	doc.save(ignore_permissions=True)

	rows = decisions.load_customers_to_create()
	rows = decisions.upsert_customer_to_create(
		rows,
		customer.name,
		{
			"customer_type": customer_type,
			"customer_group": customer_group,
			"territory": territory,
			"source_client_id": docname,
			"note": "",
		},
	)
	decisions._write_csv(
		decisions.CUSTOMERS_TO_CREATE_PATH,
		["customer_name", "customer_type", "customer_group", "territory", "source_client_id", "note"],
		rows,
	)

	frappe.db.commit()
	return customer.name
