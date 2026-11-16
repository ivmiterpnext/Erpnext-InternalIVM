"""
Sync HubSpot deals to CRM Deal records, including contacts and deployment sites.
"""

from typing import Any

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
	CONTACT_ADDRESS_PROPERTIES,
	CONTACT_FIELD_MAP,
	CONTACT_PROPERTIES,
	CONTACT_TYPE_ID,
	DEAL_FIELD_MAP,
	DEAL_TYPE_ID,
	DEALSTAGE_TO_STATUS,
	HUBSPOT_COMPANY_ID_FIELD,
	HUBSPOT_DEAL_ID_FIELD,
	HUBSPOT_DEAL_TYPE_LABELS,
	PIPELINE_MAP,
)
from ivm.integrations.hubspot.sync_utils import (
	ConcurrentCreateConflict,
	SyncLockBusy,
	apply_field_map,
	enqueue_sync,
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
	if no match is found.

	If HubSpot's closed_lost_reason is empty but doc.status (set earlier
	in the same field-map pass by _apply_status, since "dealstage" is
	ordered before "closed_lost_reason" in DEAL_FIELD_MAP) maps to a
	Lost-type CRM Deal Status, falls back to "Other" with an explanatory
	note instead of leaving lost_reason unset — CRM Deal's own
	validate_lost_reason() mandates lost_reason whenever status-type is
	"Lost", so leaving it unset here would make every subsequent save of
	this deal fail permanently (observed: 51 stuck deals in production
	where HubSpot reps never recorded a loss reason).
	"""
	value_str = str(value).strip() if value else ""

	if not value_str:
		if _is_lost_status(doc.status):
			doc.lost_reason = "Other"
			doc.lost_notes = "No reason provided by HubSpot"
			frappe.logger("hubspot").info(
				f"HubSpot closed_lost_reason was empty for a deal mapped to Lost "
				f"status '{doc.status}' — set lost_reason to 'Other' with a "
				f"placeholder note so the save doesn't fail validation"
			)
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


def _is_lost_status(status: str | None) -> bool:
	"""True if the given CRM Deal status name is of type 'Lost' per CRM Deal Status."""
	if not status:
		return False
	return frappe.get_cached_value("CRM Deal Status", status, "type") == "Lost"


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
	"""Fill a blank ``custom_customer`` from HubSpot's numeric iCorp client ID.

	HubSpot stores the iCorp numeric client ID in the ``client_id`` property
	(e.g. ``"1042"``). ``custom_customer`` is a Link -> Customer field, so the
	ID is resolved to the Customer that owns that iCorp Client Link (its name IS
	the iCorp client ID). This only fills a blank Client: a Client that is already
	set on the deal is never overwritten, and a Customer that is disabled is
	skipped (logged), so the deal stays blank for a deployer to set.
	"""
	if not value:
		return
	if getattr(doc, "custom_customer", None):
		return

	customer_name = frappe.db.get_value("iCorp Client Link", str(value), "customer")
	if not customer_name:
		frappe.logger("hubspot").warning(
			f"HubSpot client_id '{value}' did not match any assigned iCorp Client Link "
			f"— skipping custom_customer"
		)
		return

	if frappe.db.get_value("Customer", customer_name, "disabled"):
		frappe.logger("hubspot").warning(
			f"HubSpot client_id '{value}' maps to disabled Customer '{customer_name}' "
			f"— skipping custom_customer"
		)
		return

	doc.custom_customer = customer_name


DEAL_TRANSFORMS = {
	"deal_value": _apply_deal_value,
	"status": _apply_status,
	"lost_reason": _apply_lost_reason,
	"custom_pipeline": _apply_pipeline,
	"custom_deal_type": _apply_deal_type,
	"deal_owner": _apply_deal_owner,
	"custom_customer": _apply_client_id,
}


@retry_via_reenqueue(object_type_id=DEAL_TYPE_ID, id_kwarg="hubspot_deal_id")
def sync_deal(
	hubspot_deal_id: int | str,
	attempt: int = 0,
) -> None:
	"""Create-or-update a CRM Deal from the current HubSpot deal state."""
	set_acting_user()
	doc, _ = lookup_or_create(
		doctype="CRM Deal",
		hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
		hubspot_id=str(hubspot_deal_id),
		defaults={"status": "Discovery"},
	)
	_sync_deal_core(hubspot_deal_id, doc.name)


def ensure_deal_exists(hubspot_deal_id: int | str) -> str:
	"""Return the CRM Deal name for hubspot_deal_id, creating a minimal stub
	and enqueueing a full sync if it doesn't exist yet.

	Used by callers that reference a deal — engagements or deployment sites —
	which may arrive before the deal's own object.creation event has been
	processed. The stub is created immediately so the caller's own record can
	attach to it right away; field population happens asynchronously via the
	enqueued sync_deal job (enqueued after the current transaction commits,
	so the stub is guaranteed visible to the job when it runs).

	May raise ConcurrentCreateConflict or api.HubSpotRateLimitExhausted —
	callers are responsible for catching and re-enqueueing their own job.
	"""
	crm_deal_name = frappe.db.get_value(
		"CRM Deal",
		{HUBSPOT_DEAL_ID_FIELD: str(hubspot_deal_id)},
		"name",
	)
	if crm_deal_name:
		return crm_deal_name

	frappe.logger("hubspot").info(f"No CRM Deal found for HubSpot deal {hubspot_deal_id} — creating stub")
	doc, is_new = lookup_or_create(
		doctype="CRM Deal",
		hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
		hubspot_id=str(hubspot_deal_id),
		defaults={"status": "Discovery"},
	)
	if is_new:
		enqueue_sync(
			f"{__name__}.sync_deal",
			DEAL_TYPE_ID,
			str(hubspot_deal_id),
			hubspot_deal_id=str(hubspot_deal_id),
			after_commit=True,
		)
	return doc.name


def _sync_deal_core(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
	"""Sync deal-level fields and contacts.

	Deployment locations, machines, bins, and activities are no longer
	synced here — they have their own generic webhook subscriptions and
	are handled independently by ``deployment_site_handler`` and
	``activity_handler``.

	Organization is synced before deal fields so that when _sync_deal_fields
	saves the deal (triggering on_update), the organization link is already
	in place, so Customer resolution for a Won deal can find it.
	"""
	hubspot_data = api.get_deal(hubspot_deal_id, properties=list(DEAL_FIELD_MAP.keys()))
	properties: dict[str, Any] = hubspot_data.get("properties", {})

	try:
		primary_company_id, _ = api.get_deal_company_ids_by_role(hubspot_deal_id)
	except (ConcurrentCreateConflict, api.HubSpotRateLimitExhausted):
		raise
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to fetch company associations for deal {hubspot_deal_id}",
			message=frappe.get_traceback(with_context=True),
		)
		primary_company_id = None

	try:
		_sync_organization(hubspot_deal_id, crm_deal_name, primary_company_id)
	except (ConcurrentCreateConflict, api.HubSpotRateLimitExhausted):
		raise
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to sync organization for deal {crm_deal_name}",
			message=frappe.get_traceback(with_context=True),
		)

	try:
		_sync_contacts(hubspot_deal_id, crm_deal_name)
	except (ConcurrentCreateConflict, api.HubSpotRateLimitExhausted):
		raise
	except Exception:
		frappe.log_error(
			title=f"HubSpot: failed to sync contacts for deal {crm_deal_name}",
			message=frappe.get_traceback(with_context=True),
		)

	mapped_status = DEALSTAGE_TO_STATUS.get(properties.get("dealstage") or "")
	if (
		mapped_status == "Won"
		and frappe.db.get_value("CRM Deal", crm_deal_name, "status") != "Won"
		and not frappe.db.exists("Deployment Location", {"crm_deal": crm_deal_name})
	):
		from ivm.integrations.hubspot.deployment_site_handler import _sync_site_core

		site_ids: list = []
		try:
			site_ids = api.get_deal_deployment_site_ids(hubspot_deal_id)
		except (ConcurrentCreateConflict, api.HubSpotRateLimitExhausted):
			raise
		except Exception:
			frappe.log_error(
				title=f"HubSpot: failed to fetch deployment sites for Won deal {crm_deal_name}",
				message=frappe.get_traceback(with_context=True),
			)
			site_ids = []

		for site_id in site_ids:
			_sync_site_core(str(site_id), crm_deal_name, trigger_deal_sync=False)

	_sync_deal_fields(crm_deal_name, properties)


def _sync_deal_fields(crm_deal_name: str, properties: dict[str, Any]) -> None:
	"""Update deal-level fields on the CRM Deal from HubSpot deal properties."""
	deal = frappe.get_doc("CRM Deal", crm_deal_name)
	apply_field_map(deal, properties, DEAL_FIELD_MAP, DEAL_TRANSFORMS)
	save_doc(deal, "deal")


def _resolve_or_provision_org(
	hubspot_company_id: str,
	context_label: str,
) -> str | None:
	"""Look up a CRM Organization by HUBSPOT_COMPANY_ID_FIELD; if missing,
	provision it via company_handler._sync_company_core and return the name.
	Returns the CRM Organization name, or None (with a warning logged) if
	provisioning fails.

	*context_label* is used verbatim in the "skipping ..." warning (e.g.
	"organization link on deal X").
	"""
	org_name = frappe.db.get_value(
		"CRM Organization",
		{HUBSPOT_COMPANY_ID_FIELD: str(hubspot_company_id)},
		"name",
	)
	if org_name:
		return org_name

	frappe.logger("hubspot").info(
		f"No CRM Organization found for HubSpot company {hubspot_company_id} — provisioning from HubSpot"
	)
	from ivm.integrations.hubspot.company_handler import _sync_company_core

	org_name = _sync_company_core(hubspot_company_id)
	if not org_name:
		frappe.logger("hubspot").warning(
			f"Failed to provision CRM Organization for HubSpot company {hubspot_company_id} "
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

	contacts: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

	for contact_id in contact_ids:
		try:
			contact_data = api.get_contact(contact_id, properties=CONTACT_PROPERTIES)
			props = contact_data.get("properties", {})
			mapped = {frappe_key: props.get(hs_key) or "" for hs_key, frappe_key in CONTACT_FIELD_MAP.items()}
			address_props = {key: props.get(key) or "" for key in CONTACT_ADDRESS_PROPERTIES}
			contacts.append((str(contact_id), mapped, address_props))
		except Exception:
			frappe.log_error(
				title=f"HubSpot: failed to fetch contact {contact_id} for deal {hubspot_deal_id}",
				message=frappe.get_traceback(with_context=True),
			)

	if contacts:
		_ensure_contacts(crm_deal_name, contacts)


def _ensure_contacts(crm_deal_name: str, contacts: list[tuple[str, dict[str, Any], dict[str, Any]]]) -> None:
	"""Create Contact records (if needed) and link them to the CRM Deal.

	Acquires a per-contact lock before each upsert to prevent races with
	direct contact webhooks (which also sync the same Contact via sync_contact).

	Exception handling: ConcurrentCreateConflict, HubSpotRateLimitExhausted,
	TimestampMismatchError and SyncLockBusy are re-raised, and so is a failure to
	acquire a contact's lock (SyncLockBusy is raised instead of skipping the contact).
	They propagate out of
	this function to sync_deal's @retry_via_reenqueue, which re-enqueues the WHOLE
	deal sync (sync_deal re-runs _sync_deal_core -> _sync_contacts -> this function
	from the top, re-fetching every contact). Consequence: when one contact hits
	one of these, the contacts after it in the list are NOT processed in this
	attempt, and nothing from this call is linked to the deal (the link step runs
	only after the loop). A fresh full retry is intended in that case. Any other
	exception is logged to the Error Log and that contact is skipped (continue);
	the remaining contacts are still processed.

	The per-contact lock is released (finally) whenever it was acquired, whether
	the exception propagates or not. If the lock could not be acquired, no lock is
	held, so nothing is released and SyncLockBusy propagates immediately.
	"""
	from ivm.integrations.hubspot.contact_handler import upsert_contact

	resolved: list[tuple[str, int]] = []
	for idx, (contact_id, entry, address_props) in enumerate(contacts):
		lock_key = frappe.cache.make_key(f"hubspot_sync_lock:{CONTACT_TYPE_ID}:{contact_id}")
		lock = frappe.cache.lock(lock_key, timeout=1500, blocking_timeout=30)

		if not lock.acquire():
			# Nothing was acquired, so there is no lock to release here: this raise
			# happens before the try/finally below on purpose.
			raise SyncLockBusy(CONTACT_TYPE_ID, contact_id)

		try:
			try:
				contact_name = upsert_contact(
					entry, hubspot_contact_id=contact_id, address_props=address_props
				)
			except (
				ConcurrentCreateConflict,
				api.HubSpotRateLimitExhausted,
				frappe.exceptions.TimestampMismatchError,
				SyncLockBusy,
			):
				raise
			except Exception:
				frappe.log_error(
					title=f"HubSpot: failed to upsert contact for deal {crm_deal_name}",
					message=frappe.get_traceback(with_context=True),
				)
				continue

			if not contact_name:
				continue

			resolved.append((contact_name, 1 if idx == 0 else 0))
		finally:
			try:
				lock.release()
			except Exception:
				pass

	if not resolved:
		return

	def _apply_contacts(d: Any) -> None:
		existing = {row.contact for row in (d.get("contacts") or [])}
		for contact_name, is_primary in resolved:
			if contact_name in existing:
				continue
			if is_primary:
				for row in d.get("contacts") or []:
					row.is_primary = 0
			d.append("contacts", {"contact": contact_name, "is_primary": is_primary})
			existing.add(contact_name)

	deal = frappe.get_doc("CRM Deal", crm_deal_name)
	_apply_contacts(deal)
	save_doc(deal, "deal", mutate=_apply_contacts)
