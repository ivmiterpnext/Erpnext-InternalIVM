"""
Sync HubSpot deals to CRM Deal records, including contacts and deployment sites.
"""

from typing import Any

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
	CONTACT_FIELD_MAP,
	DEAL_FIELD_MAP,
	DEALSTAGE_TO_STATUS,
	HUBSPOT_COMPANY_ID_FIELD,
	HUBSPOT_DEAL_ID_FIELD,
	HUBSPOT_DEAL_TYPE_LABELS,
	PIPELINE_MAP,
)
from ivm.integrations.hubspot.sync_utils import (
	ConcurrentCreateConflict,
	apply_field_map,
	lookup_or_create,
	retry_via_reenqueue,
	save_doc,
	set_acting_user,
)


def _apply_deal_value(doc: Any, value: Any) -> None:
	doc.deal_value = frappe.utils.flt(value)


def _apply_status(doc: Any, value: Any) -> None:
	mapped = DEALSTAGE_TO_STATUS.get(value or "")
	if mapped:
		doc.status = mapped


def _apply_lost_reason(doc: Any, value: Any) -> None:
	"""Map a HubSpot closed_lost_reason to a CRM Lost Reason record.

	Attempts case-insensitive matching against existing CRM Lost Reason
	records.  Falls back to "Other" with the raw value in ``lost_notes``
	if no match is found.  Only applies when the deal status is "Lost".
	"""
	if not value:
		return

	value_str = str(value).strip()
	if not value_str:
		return

	# Build a case-insensitive lookup of existing lost reasons
	existing = frappe.get_all("CRM Lost Reason", pluck="name")
	lookup = {name.lower(): name for name in existing}

	matched = lookup.get(value_str.lower())
	if matched:
		doc.lost_reason = matched
	else:
		doc.lost_reason = "Other"
		doc.lost_notes = value_str
		frappe.logger("hubspot").info(
			f"HubSpot closed_lost_reason '{value_str}' did not match any "
			f"CRM Lost Reason — set to 'Other' with lost_notes"
		)


def _apply_pipeline(doc: Any, value: Any) -> None:
	mapped = PIPELINE_MAP.get(value or "")
	if mapped:
		if frappe.db.exists("CRM Pipeline", mapped):
			doc.custom_pipeline = mapped
		else:
			frappe.logger("hubspot").warning(
				f"CRM Pipeline '{mapped}' (from HubSpot pipeline '{value}') "
				f"not found — skipping custom_pipeline"
			)
	elif value:
		frappe.logger("hubspot").warning(f"Unknown HubSpot pipeline ID '{value}' — skipping custom_pipeline")


def _apply_deal_type(doc: Any, value: Any) -> None:
	if not value:
		return
	label = HUBSPOT_DEAL_TYPE_LABELS.get(value)
	if label:
		doc.custom_deal_type = label
	else:
		frappe.logger("hubspot").warning(f"Unknown HubSpot dealtype '{value}' — skipping custom_deal_type")


def _apply_deal_owner(doc: Any, value: Any) -> None:
	if not value:
		return
	owner_email = api.get_owner_email(value)
	if owner_email and frappe.db.exists("User", owner_email):
		doc.deal_owner = owner_email
	else:
		frappe.logger("hubspot").warning(
			f"HubSpot owner {value} resolved to '{owner_email}' "
			f"which is not a Frappe User — skipping deal_owner"
		)


def _apply_client_id(doc: Any, value: Any) -> None:
	"""Resolve HubSpot's numeric iCorp client ID to a Frappe Customer name.

	HubSpot stores the iCorp numeric client ID in the ``client_id`` property
	(e.g. ``"1042"``).  ``custom_customer`` is a Link → Customer field, so
	we must look up the Customer whose ``icorp_client_id`` matches before
	writing the value, otherwise Frappe silently discards the raw numeric string.
	"""
	if not value:
		return
	customer_name = frappe.db.get_value("Customer", {"icorp_client_id": str(value)}, "name")
	if customer_name:
		doc.custom_customer = customer_name
	else:
		frappe.logger("hubspot").warning(
			f"HubSpot client_id '{value}' did not match any Customer "
			f"(icorp_client_id) — skipping custom_customer"
		)


DEAL_TRANSFORMS = {
	"deal_value": _apply_deal_value,
	"status": _apply_status,
	"lost_reason": _apply_lost_reason,
	"custom_pipeline": _apply_pipeline,
	"custom_deal_type": _apply_deal_type,
	"deal_owner": _apply_deal_owner,
	"custom_customer": _apply_client_id,
}


@retry_via_reenqueue()
def handle_deal_created(
	hubspot_deal_id: int | str,
	hubspot_user_id: int | str | None = None,
) -> None:
	"""Create a CRM Deal from a newly created HubSpot deal and sync all data."""
	set_acting_user(hubspot_user_id)
	try:
		doc, is_new = lookup_or_create(
			doctype="CRM Deal",
			hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
			hubspot_id=str(hubspot_deal_id),
			defaults={"status": "Discovery"},
		)
		if not is_new:
			frappe.logger("hubspot").info(
				f"CRM Deal already exists for HubSpot deal {hubspot_deal_id} "
				f"(created by a concurrent event or self-heal) — skipping duplicate creation"
			)
			return
		_sync_deal(hubspot_deal_id, doc.name)
	except (ConcurrentCreateConflict, api.HubSpotRateLimitExhausted):
		raise
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to create CRM Deal for deal {hubspot_deal_id}",
			message=frappe.get_traceback(with_context=True),
		)


@retry_via_reenqueue()
def handle_deal_updated(
	hubspot_deal_id: int | str,
	hubspot_user_id: int | str | None = None,
) -> None:
	"""Sync a HubSpot deal's current state to the matching CRM Deal.

	Creates the CRM Deal first (via ensure_deal_exists) if it doesn't exist
	yet — a propertyChange or associationChange event can arrive for a deal
	whose object.creation event was missed, deduplicated away, or not yet
	processed.
	"""
	set_acting_user(hubspot_user_id)
	try:
		crm_deal_name, was_created = ensure_deal_exists(hubspot_deal_id, hubspot_user_id)
		if not was_created:
			_sync_deal(hubspot_deal_id, crm_deal_name)
	except (ConcurrentCreateConflict, api.HubSpotRateLimitExhausted):
		raise
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to sync deal {hubspot_deal_id}",
			message=frappe.get_traceback(with_context=True),
		)


def ensure_deal_exists(
	hubspot_deal_id: int | str,
	hubspot_user_id: int | str | None = None,
) -> tuple[str, bool]:
	"""Return (crm_deal_name, was_created) for hubspot_deal_id.

	Creates the CRM Deal (and fully syncs it via _sync_deal) if it doesn't
	exist yet. Used by callers that reference a deal — engagements,
	deployment sites, or the deal's own propertyChange/associationChange
	events — which may arrive before the deal's own object.creation event
	has been processed (missed, deduplicated, or simply not yet run).

	May raise ConcurrentCreateConflict or api.HubSpotRateLimitExhausted —
	callers are responsible for catching and re-enqueueing their own job.
	"""
	crm_deal_name = frappe.db.get_value(
		"CRM Deal",
		{HUBSPOT_DEAL_ID_FIELD: str(hubspot_deal_id)},
		"name",
	)
	if crm_deal_name:
		return crm_deal_name, False

	frappe.logger("hubspot").info(f"No CRM Deal found for HubSpot deal {hubspot_deal_id} — creating")
	doc, _ = lookup_or_create(
		doctype="CRM Deal",
		hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
		hubspot_id=str(hubspot_deal_id),
		defaults={"status": "Discovery"},
	)
	_sync_deal(hubspot_deal_id, doc.name)
	return doc.name, True


def _sync_deal(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
	"""Sync deal-level fields and contacts.

	Deployment locations, machines, bins, and activities are no longer
	synced here — they have their own generic webhook subscriptions and
	are handled independently by ``deployment_site_handler`` and
	``activity_handler``.

	Organization is synced before deal fields so that when _sync_deal_fields
	saves the deal (triggering on_update), the organization link is already
	in place — ensuring customer provisioning can find it if the deal is Won.
	"""
	hubspot_data = api.get_deal(hubspot_deal_id, properties=list(DEAL_FIELD_MAP.keys()))
	properties: dict[str, Any] = hubspot_data.get("properties", {})

	# Fetch company associations once and pass both primary and master IDs
	try:
		primary_company_id, master_company_id = api.get_deal_company_ids_by_role(hubspot_deal_id)
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to fetch company associations for deal {hubspot_deal_id}",
			message=frappe.get_traceback(with_context=True),
		)
		primary_company_id = None
		master_company_id = None

	try:
		_sync_organization(hubspot_deal_id, crm_deal_name, primary_company_id)
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to sync organization for deal {crm_deal_name}",
			message=frappe.get_traceback(with_context=True),
		)

	try:
		_sync_master_organization(hubspot_deal_id, crm_deal_name, master_company_id)
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to sync master organization for deal {crm_deal_name}",
			message=frappe.get_traceback(with_context=True),
		)

	try:
		_sync_contacts(hubspot_deal_id, crm_deal_name)
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to sync contacts for deal {crm_deal_name}",
			message=frappe.get_traceback(with_context=True),
		)

	_sync_deal_fields(crm_deal_name, properties)


def _sync_deal_fields(crm_deal_name: str, properties: dict[str, Any]) -> None:
	"""Update deal-level fields on the CRM Deal from HubSpot deal properties."""
	deal = frappe.get_doc("CRM Deal", crm_deal_name)
	apply_field_map(deal, properties, DEAL_FIELD_MAP, DEAL_TRANSFORMS)
	save_doc(deal, "deal")


def _resolve_or_provision_org(
	hubspot_company_id: str,
	context_label: str,
	company_label: str = "company",
) -> str | None:
	"""Look up a CRM Organization by HUBSPOT_COMPANY_ID_FIELD; if missing,
	provision it via company_handler.handle_company_created and look up
	again. Returns the CRM Organization name, or None (with a warning
	logged) if it still can't be found after provisioning.

	*context_label* is used verbatim in the "skipping ..." warning (e.g.
	"organization link on deal X" or "master link on deal X").
	*company_label* is used in the "HubSpot {company_label} {id}" phrasing
	(e.g. "company" or "master company").
	"""
	org_name = frappe.db.get_value(
		"CRM Organization",
		{HUBSPOT_COMPANY_ID_FIELD: str(hubspot_company_id)},
		"name",
	)
	if org_name:
		return org_name

	frappe.logger("hubspot").info(
		f"No CRM Organization found for HubSpot {company_label} {hubspot_company_id} "
		f"— provisioning from HubSpot"
	)
	from ivm.integrations.hubspot.company_handler import handle_company_created

	handle_company_created(hubspot_company_id)
	org_name = frappe.db.get_value(
		"CRM Organization",
		{HUBSPOT_COMPANY_ID_FIELD: str(hubspot_company_id)},
		"name",
	)
	if not org_name:
		frappe.logger("hubspot").warning(
			f"Failed to provision CRM Organization for HubSpot {company_label} {hubspot_company_id} "
			f"— skipping {context_label}"
		)
		return None

	return org_name


def _sync_organization(
	hubspot_deal_id: int | str, crm_deal_name: str, primary_company_id: str | None
) -> None:
	"""Link the primary associated HubSpot company to the CRM Deal's organization field."""
	if not primary_company_id:
		return

	org_name = _resolve_or_provision_org(
		primary_company_id,
		f"organization link on deal {crm_deal_name}",
	)
	if not org_name:
		return

	deal = frappe.get_doc("CRM Deal", crm_deal_name)
	if deal.organization == org_name:
		return

	deal.organization = org_name
	save_doc(deal, "deal")
	frappe.logger("hubspot").info(f"Linked CRM Organization '{org_name}' to CRM Deal {crm_deal_name}")


def _sync_master_organization(
	hubspot_deal_id: int | str, crm_deal_name: str, master_company_id: str | None
) -> None:
	"""Link the master-labeled associated HubSpot company to the CRM Deal,
	populating exactly one of custom_master_customer (if the master already
	exists as a Customer) or custom_master_organization (if it doesn't yet)
	— never both at once.

	Checks for an existing Customer match directly against raw HubSpot
	company data first (name + website only — industry is deliberately
	skipped here since it requires the HUBSPOT_INDUSTRY_LABELS mapping,
	which today only happens inside company_handler.py, and
	_find_existing_customer treats industry as an optional secondary filter
	anyway, not a required field). This avoids provisioning a CRM
	Organization record for master companies that turn out to already be
	existing Customers — a CRM Organization is only created as a fallback,
	when no Customer match is found.

	Unlike the primary client, there's no custom_deal_type-equivalent flag
	telling us upfront whether the master client is new or already an
	existing Customer — so we always look it up here rather than branching
	on a flag. Never overwrites an already-resolved custom_master_customer
	(whether set manually in Frappe or by a prior sync) — once known, it's
	known.
	"""
	if not master_company_id:
		return

	deal = frappe.get_doc("CRM Deal", crm_deal_name)

	if deal.custom_master_customer:
		return

	from ivm.deployments.services.provision_client_from_deal import _find_existing_customer

	try:
		company_data = api.get_company(master_company_id, properties=["name", "website"])
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to fetch master company {master_company_id} for deal {crm_deal_name}",
			message=frappe.get_traceback(with_context=True),
		)
		return

	company_props = company_data.get("properties", {})
	company_name = (company_props.get("name") or "").strip()

	existing_customer = None
	if company_name:
		company_like = frappe._dict(
			{
				"organization_name": company_name,
				"website": company_props.get("website"),
				"industry": None,
			}
		)
		existing_customer = _find_existing_customer(company_like)

	changed = False

	if existing_customer:
		deal.custom_master_customer = existing_customer
		changed = True
		if deal.custom_master_organization:
			deal.custom_master_organization = ""
		frappe.logger("hubspot").info(
			f"Master company '{master_company_id}' matches existing Customer "
			f"'{existing_customer}' — linked directly on deal {crm_deal_name}"
		)
	else:
		org_name = _resolve_or_provision_org(
			master_company_id,
			f"master link on deal {crm_deal_name}",
			company_label="master company",
		)
		if not org_name:
			return

		if deal.custom_master_organization != org_name:
			deal.custom_master_organization = org_name
			changed = True

	if not changed:
		return

	save_doc(deal, "deal")
	frappe.logger("hubspot").info(f"Synced master client for CRM Deal {crm_deal_name}")


def _sync_contacts(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
	"""Fetch contacts associated with the HubSpot deal and link them to the CRM Deal."""
	try:
		contact_ids = api.get_deal_contact_ids(hubspot_deal_id)
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to fetch contact associations for deal {hubspot_deal_id}",
			message=frappe.get_traceback(with_context=True),
		)
		return

	if not contact_ids:
		return

	hs_properties = list(CONTACT_FIELD_MAP.keys())
	contacts: list[dict[str, Any]] = []

	for contact_id in contact_ids:
		try:
			contact_data = api.get_contact(contact_id, properties=hs_properties)
			props = contact_data.get("properties", {})
			contacts.append(
				{frappe_key: props.get(hs_key) or "" for hs_key, frappe_key in CONTACT_FIELD_MAP.items()}
			)
		except Exception:
			frappe.log_error(
				title=f"HubSpot: failed to fetch contact {contact_id} for deal {hubspot_deal_id}",
				message=frappe.get_traceback(with_context=True),
			)

	if contacts:
		_ensure_contacts(crm_deal_name, contacts)


def _ensure_contacts(crm_deal_name: str, contacts: list[dict[str, Any]]) -> None:
	"""Create Contact records (if needed) and link them to the CRM Deal."""
	from ivm.integrations.hubspot.contact_handler import upsert_contact

	resolved: list[tuple[str, int]] = []
	for idx, entry in enumerate(contacts):
		try:
			contact_name = upsert_contact(entry)
		except Exception:
			frappe.log_error(
				title=f"HubSpot: failed to upsert contact for deal {crm_deal_name}",
				message=frappe.get_traceback(with_context=True),
			)
			continue

		if not contact_name:
			continue

		resolved.append((contact_name, 1 if idx == 0 else 0))

	if not resolved:
		return

	def _apply_contacts(d: Any) -> None:
		existing = {row.contact for row in (d.get("contacts") or [])}
		for contact_name, is_primary in resolved:
			if contact_name in existing:
				continue
			d.append("contacts", {"contact": contact_name, "is_primary": is_primary})
			existing.add(contact_name)

	deal = frappe.get_doc("CRM Deal", crm_deal_name)
	_apply_contacts(deal)
	save_doc(deal, "deal", mutate=_apply_contacts)
