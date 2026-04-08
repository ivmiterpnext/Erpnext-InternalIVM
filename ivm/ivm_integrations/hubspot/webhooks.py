import json
from datetime import UTC, datetime
from typing import Final

import frappe
import requests
from frappe.exceptions import DuplicateEntryError

from ivm.ivm_integrations.hubspot.constants import (
	HUBSPOT_API_BASE_URL,
	HUBSPOT_CUSTOM_OBJECT_URL,
	HUBSPOT_DEAL_CREATION_SUBSCRIPTION_TYPE,
	HUBSPOT_DEAL_PROPERTY_CHANGE_SUBSCRIPTION_TYPE,
	HUBSPOT_DEAL_PROPERTY_KEYS,
	HUBSPOT_DEPLOYMENT_SITES_OBJECT_TYPE,
	HUBSPOT_EVENT_SUBSCRIPTION_TYPES,
)

HUBSPOT_SETTINGS_DOCTYPE: Final[str] = "HubSpot Settings"
HUBSPOT_STAGE_MAPPING_DOCTYPE: Final[str] = "HubSpot Stage Mapping"
WEBHOOK_EVENT_DOCTYPE: Final[str] = "HubSpot Webhook Event"
CRM_DEAL_DOCTYPE: Final[str] = "CRM Deal"
DEPLOYMENT_SITE_CHILD_DOCTYPE: Final[str] = "Deployment Site"
PROJECT_DOCTYPE: Final[str] = "Project"


@frappe.whitelist(allow_guest=True)
def handle() -> dict[str, int | str]:
	"""Receive HubSpot webhooks, validate authenticity, and enqueue processing.

	Accepted event types:
	  - deal.creation: A new deal was created in HubSpot.
	  - deal.propertyChange: A deal property was changed (we process all
	    dealstage changes to track the full deal lifecycle).
	"""
	request_body = frappe.request.get_data(as_text=True) or ""

	events = _parse_events(request_body)
	queued = 0
	ignored = 0

	for event in events:
		if not _is_relevant_deal_event(event):
			ignored += 1
			continue

		log_name = _insert_event_log(event=event)
		if not log_name:
			ignored += 1
			continue

		frappe.enqueue(
			"ivm.ivm_integrations.hubspot.webhooks.process_deal_event",
			queue="short",
			event_log_name=log_name,
		)
		queued += 1

	return {"status": "ok", "queued": queued, "ignored": ignored}


def process_deal_event(event_log_name: str) -> None:
	"""Worker entry point: process a deal creation or property-change event.

	For **deal.creation** events:
	  1. Fetch deal properties from the HubSpot API.
	  2. Create a CRM Deal populated with all available properties.
	  3. If the initial deal stage maps to a closed-won status, also fetch
	     deployment sites and create Projects.

	For **deal.propertyChange** events (dealstage changes):
	  1. Fetch deal properties from the HubSpot API.
	  2. Upsert the CRM Deal with current properties and the mapped status.
	  3. If the new deal stage maps to a closed-won status, fetch deployment
	     sites and create Projects.
	"""
	event_log = frappe.get_doc(WEBHOOK_EVENT_DOCTYPE, event_log_name)
	if event_log.status == "Processed":
		return

	event_log.db_set("status", "Queued")

	try:
		deal_id = str(event_log.object_id or "").strip()
		if not deal_id:
			raise frappe.ValidationError("HubSpot webhook event is missing object_id.")

		access_token = _get_access_token()
		deal_properties = _fetch_deal_properties(
			deal_id=deal_id, access_token=access_token
		)

		hubspot_stage = deal_properties.get("dealstage") or ""
		crm_status, is_closed_won = _resolve_deal_status(hubspot_stage)

		deal_doc = _upsert_deal(
			hubspot_deal_id=deal_id,
			deal_properties=deal_properties,
			crm_status=crm_status,
		)

		if is_closed_won:
			_process_closed_won(
				deal_doc=deal_doc,
				deal_id=deal_id,
				access_token=access_token,
			)

		event_log.db_set("status", "Processed")
	except Exception:
		frappe.log_error(
			title="HubSpot deal event processing failed",
			message=frappe.get_traceback(with_context=True),
		)
		event_log.db_set("status", "Failed")
		raise


# ---------------------------------------------------------------------------
# HubSpot API helpers
# ---------------------------------------------------------------------------


def _get_access_token() -> str:
	"""Read the decrypted access_token from HubSpot Settings."""
	token = frappe.utils.password.get_decrypted_password(
		HUBSPOT_SETTINGS_DOCTYPE,
		HUBSPOT_SETTINGS_DOCTYPE,
		"access_token",
	)
	if not token:
		raise frappe.ValidationError("HubSpot Settings: access_token is not configured.")
	return token


def _fetch_deal_properties(*, deal_id: str, access_token: str) -> dict:
	"""Fetch deal properties from the HubSpot CRM v3 deals API.

	Requests all properties listed in ``HUBSPOT_DEAL_PROPERTY_KEYS`` and
	returns the ``properties`` dict from the response (or an empty dict on
	failure).
	"""
	url = f"{HUBSPOT_API_BASE_URL}/crm/v3/objects/deals/{deal_id}"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Accept": "application/json",
	}
	params = {
		"properties": ",".join(HUBSPOT_DEAL_PROPERTY_KEYS.values()),
	}

	try:
		response = requests.get(url, headers=headers, params=params, timeout=30)
	except requests.RequestException as exc:
		frappe.log_error(
			title="HubSpot API request failed for deal",
			message={"deal_id": deal_id, "error": str(exc)},
		)
		return {}

	if response.status_code != 200:
		frappe.log_error(
			title="HubSpot API error fetching deal properties",
			message={
				"deal_id": deal_id,
				"status_code": response.status_code,
				"response": response.text[:2000],
			},
		)
		return {}

	data = response.json()
	return data.get("properties") or {}


def _fetch_deployment_site_ids(*, deal_id: str, access_token: str) -> list[str]:
	"""GET deployment_sites associations for a HubSpot deal.

	Uses the CRM v4 associations API with pagination support.
	Returns a deduplicated list of associated object IDs.
	"""
	url = (
		f"{HUBSPOT_API_BASE_URL}/crm/v4/objects/deals/{deal_id}"
		f"/associations/{HUBSPOT_DEPLOYMENT_SITES_OBJECT_TYPE}"
	)
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Accept": "application/json",
	}

	site_ids: list[str] = []
	seen: set[str] = set()

	while url:
		response = requests.get(url, headers=headers, timeout=30)

		if response.status_code != 200:
			frappe.log_error(
				title="HubSpot API error fetching deployment site associations",
				message={
					"deal_id": deal_id,
					"status_code": response.status_code,
					"response": response.text[:2000],
				},
			)
			raise frappe.ValidationError(
				f"HubSpot API returned {response.status_code} when fetching "
				f"deployment site associations for deal {deal_id}."
			)

		data = response.json()

		for result in data.get("results", []):
			to_object_id = str(result.get("toObjectId") or "").strip()
			if to_object_id and to_object_id not in seen:
				seen.add(to_object_id)
				site_ids.append(to_object_id)

		# Handle pagination
		paging = data.get("paging")
		next_link = (paging or {}).get("next", {}).get("link")
		url = next_link if next_link else None

	return site_ids


# ---------------------------------------------------------------------------
# Deployment site property fetching
# ---------------------------------------------------------------------------


def _fetch_deployment_site_properties(*, site_id: str, access_token: str) -> dict:
	"""Fetch all properties for a single HubSpot deployment site custom object.

	Returns the ``properties`` dict from the HubSpot response, or an empty
	dict if the call fails (errors are logged but do **not** prevent project
	creation).
	"""
	path = HUBSPOT_CUSTOM_OBJECT_URL.format(
		object_type=HUBSPOT_DEPLOYMENT_SITES_OBJECT_TYPE,
		object_id=site_id,
	)
	url = f"{HUBSPOT_API_BASE_URL}{path}"
	headers = {
		"Authorization": f"Bearer {access_token}",
		"Accept": "application/json",
	}
	params = {"propertiesWithHistory": "false"}

	try:
		response = requests.get(url, headers=headers, params=params, timeout=30)
	except requests.RequestException as exc:
		frappe.log_error(
			title="HubSpot API request failed for deployment site",
			message={"site_id": site_id, "error": str(exc)},
		)
		return {}

	if response.status_code != 200:
		frappe.log_error(
			title="HubSpot API error fetching deployment site properties",
			message={
				"site_id": site_id,
				"status_code": response.status_code,
				"response": response.text[:2000],
			},
		)
		return {}

	data = response.json()
	return data.get("properties") or {}


# ---------------------------------------------------------------------------
# Deal status resolution
# ---------------------------------------------------------------------------


def _resolve_deal_status(hubspot_stage: str) -> tuple[str | None, bool]:
	"""Map a HubSpot deal-stage ID to a CRM Deal Status using the
	HubSpot Stage Mapping doctype.

	Returns:
		A tuple of (crm_deal_status, is_closed_won).
		If no mapping is found, returns (None, False).
	"""
	if not hubspot_stage:
		return None, False

	mapping = frappe.db.get_value(
		HUBSPOT_STAGE_MAPPING_DOCTYPE,
		{"hubspot_stage_id": hubspot_stage},
		["crm_deal_status", "is_closed_won"],
		as_dict=True,
	)

	if not mapping:
		frappe.log_error(
			title="No HubSpot Stage Mapping found",
			message={
				"hubspot_stage": hubspot_stage,
				"hint": (
					"Create a HubSpot Stage Mapping record for this stage ID "
					"so that incoming deals can be mapped to a CRM Deal Status."
				),
			},
		)
		return None, False

	return mapping.crm_deal_status, bool(mapping.is_closed_won)


# ---------------------------------------------------------------------------
# CRM Deal upsert
# ---------------------------------------------------------------------------


def _upsert_deal(
	*,
	hubspot_deal_id: str,
	deal_properties: dict,
	crm_status: str | None,
) -> object:
	"""Find or create the CRM Deal and update it with the latest HubSpot
	deal properties.

	Returns the saved CRM Deal document.
	"""
	existing_name = frappe.db.get_value(
		CRM_DEAL_DOCTYPE, {"hubspot_deal_id": hubspot_deal_id}, "name"
	)

	field_values = _map_deal_properties(deal_properties)

	if existing_name:
		deal_doc = frappe.get_doc(CRM_DEAL_DOCTYPE, existing_name)
		for field, value in field_values.items():
			if value is not None:
				deal_doc.set(field, value)
	else:
		doc_dict = {
			"doctype": CRM_DEAL_DOCTYPE,
			"hubspot_deal_id": hubspot_deal_id,
		}
		for field, value in field_values.items():
			if value is not None:
				doc_dict[field] = value
		deal_doc = frappe.get_doc(doc_dict)

	if crm_status:
		deal_doc.status = crm_status

	if existing_name:
		deal_doc.save(ignore_permissions=True)
	else:
		deal_doc.insert(ignore_permissions=True, ignore_mandatory=True)

	return deal_doc


def _map_deal_properties(deal_properties: dict) -> dict:
	"""Convert raw HubSpot deal properties into CRM Deal field values using
	the ``HUBSPOT_DEAL_PROPERTY_KEYS`` mapping.

	Returns a dict of {crm_field: value} with only non-empty values.
	"""
	mapped: dict = {}

	for crm_field, hs_key in HUBSPOT_DEAL_PROPERTY_KEYS.items():
		raw = deal_properties.get(hs_key)
		if raw is None or str(raw).strip() == "":
			continue

		# Skip fields that are resolved separately (status via stage mapping)
		if crm_field == "stage_id":
			continue

		mapped[crm_field] = str(raw).strip()

	# Convert numeric fields
	if "amount" in mapped:
		try:
			mapped["amount"] = float(mapped["amount"])
		except (ValueError, TypeError):
			del mapped["amount"]

	return mapped


# ---------------------------------------------------------------------------
# Closed-won processing: deployment sites + project creation
# ---------------------------------------------------------------------------


def _process_closed_won(
	*, deal_doc: object, deal_id: str, access_token: str
) -> None:
	"""Handle closed-won logic: fetch deployment site associations, update the
	CRM Deal's deployment_sites child table, and create Projects."""
	site_ids = _fetch_deployment_site_ids(deal_id=deal_id, access_token=access_token)

	# Clear and repopulate the deployment_sites child table
	deal_doc.set("deployment_sites", [])
	for site_id in site_ids:
		deal_doc.append("deployment_sites", {"site_id": site_id})
	deal_doc.save(ignore_permissions=True)

	# Create a Project for each deployment site that doesn't already have one
	_create_projects_for_sites(
		deal_doc=deal_doc, site_ids=site_ids, access_token=access_token
	)


# ---------------------------------------------------------------------------
# Project creation per deployment site
# ---------------------------------------------------------------------------


def _create_projects_for_sites(
	*, deal_doc: object, site_ids: list[str], access_token: str
) -> None:
	"""Create one Project for every deployment site ID that does not already
	have a corresponding Project linked to this CRM Deal.

	Each Project stores the ``custom_deployment_site_id`` for idempotency and
	the full HubSpot properties payload in ``custom_hubspot_site_data``.
	"""
	default_company = frappe.db.get_single_value(HUBSPOT_SETTINGS_DOCTYPE, "default_company")
	if not default_company:
		frappe.log_error(
			title="Skipping project creation - missing HubSpot Settings.default_company",
			message={"crm_deal": deal_doc.name},
		)
		return

	org_name = (
		deal_doc.get("organization_name")
		or deal_doc.get("organization")
		or deal_doc.get("name_1")
		or deal_doc.name
	)

	for site_id in site_ids:
		# Idempotency: skip if a Project already exists for this deal + site
		if frappe.db.exists(
			PROJECT_DOCTYPE,
			{"crm_deal": deal_doc.name, "custom_deployment_site_id": site_id},
		):
			continue

		site_properties = _fetch_deployment_site_properties(
			site_id=site_id, access_token=access_token
		)

		site_label = (
			site_properties.get("name")
			or site_properties.get("hs_object_id")
			or site_id
		)
		project_name = f"{org_name} - {site_label}"

		project_doc = frappe.get_doc(
			{
				"doctype": PROJECT_DOCTYPE,
				"project_name": project_name,
				"company": default_company,
				"crm_deal": deal_doc.name,
				"custom_deployment_site_id": site_id,
				"custom_hubspot_site_data": json.dumps(site_properties, default=str),
			}
		)

		try:
			project_doc.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="Failed creating Project for deployment site",
				message={
					"crm_deal": deal_doc.name,
					"site_id": site_id,
					"traceback": frappe.get_traceback(with_context=True),
				},
			)


# ---------------------------------------------------------------------------
# Event parsing and filtering
# ---------------------------------------------------------------------------


def _parse_events(request_body: str) -> list[dict[str, object]]:
	try:
		event_list = json.loads(request_body or "[]")
	except json.JSONDecodeError as exc:
		raise frappe.ValidationError("HubSpot webhook body must be valid JSON.") from exc

	if not isinstance(event_list, list):
		raise frappe.ValidationError("HubSpot webhook body must be an array.")

	events: list[dict[str, object]] = []
	for item in event_list:
		if isinstance(item, dict):
			events.append(item)

	return events


def _is_relevant_deal_event(event: dict[str, object]) -> bool:
	"""Return True for deal events we should process.

	Accepted events:
	  - deal.creation: always relevant (a new deal was created).
	  - deal.propertyChange: relevant when the ``propertyName`` is
	    ``dealstage``, meaning the deal's pipeline stage was changed.
	"""
	subscription_type = str(event.get("subscriptionType") or "")
	object_id = event.get("objectId")

	if not object_id:
		return False

	if subscription_type not in HUBSPOT_EVENT_SUBSCRIPTION_TYPES:
		return False

	if subscription_type == HUBSPOT_DEAL_CREATION_SUBSCRIPTION_TYPE:
		return True

	if subscription_type == HUBSPOT_DEAL_PROPERTY_CHANGE_SUBSCRIPTION_TYPE:
		property_name = str(event.get("propertyName") or "").strip().lower()
		return property_name == "dealstage"

	return False


def _insert_event_log(*, event: dict[str, object]) -> str | None:
	object_id = str(event.get("objectId") or "")
	subscription_type = str(event.get("subscriptionType") or "")
	occurred_at_raw = _coerce_int(event.get("occurredAt"))
	occurred_at = _to_datetime(occurred_at_raw)
	event_key = f"{object_id}:{subscription_type}:{occurred_at_raw}"

	log_doc = frappe.get_doc(
		{
			"doctype": WEBHOOK_EVENT_DOCTYPE,
			"event_key": event_key,
			"object_id": object_id,
			"subscription_type": subscription_type,
			"occurred_at": occurred_at,
			"status": "Queued",
		}
	)

	try:
		log_doc.insert(ignore_permissions=True)
	except DuplicateEntryError:
		return None

	return log_doc.name


def _to_datetime(value: int) -> datetime:
	if value > 10**10:
		seconds = value / 1000
	else:
		seconds = value

	return datetime.fromtimestamp(seconds, tz=UTC).replace(tzinfo=None)


def _coerce_int(value: object) -> int:
	if isinstance(value, bool):
		return int(value)

	if isinstance(value, int):
		return value

	if isinstance(value, float):
		return int(value)

	if isinstance(value, str):
		try:
			return int(value)
		except ValueError:
			return 0

	return 0
