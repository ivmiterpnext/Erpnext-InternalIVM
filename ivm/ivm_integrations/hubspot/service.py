"""HubSpot webhook event processing for CRM Deal upserts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

import frappe
from frappe.model.document import Document

from ivm.ivm_integrations.hubspot.constants import HUBSPOT_DEAL_PROPERTY_KEYS

WEBHOOK_EVENT_DOCTYPE: Final[str] = "HubSpot Webhook Event"
CRM_DEAL_DOCTYPE: Final[str] = "CRM Deal"


def sync_deal_from_event_log(*, event_log_name: str) -> None:
	"""Create or update CRM Deal from a single webhook event log."""
	event_log = frappe.get_doc(WEBHOOK_EVENT_DOCTYPE, event_log_name)
	event_data = _build_event_data(event_log)

	deal_id = str(event_data.get("objectId") or "").strip()
	if not deal_id:
		raise frappe.ValidationError("HubSpot webhook event is missing objectId.")

	updates = _build_crm_updates(event_data=event_data, event_log=event_log, deal_id=deal_id)
	if not updates:
		return

	upsert_crm_deal(hubspot_deal_id=deal_id, updates=updates)


def upsert_crm_deal(*, hubspot_deal_id: str, updates: dict[str, object]) -> str:
	"""Upsert CRM Deal by unique hubspot_deal_id and apply changed fields only."""
	existing_name = frappe.db.get_value(CRM_DEAL_DOCTYPE, {"hubspot_deal_id": hubspot_deal_id}, "name")
	if existing_name:
		deal_doc = frappe.get_doc(CRM_DEAL_DOCTYPE, existing_name)
		if _apply_changed_fields(deal_doc, updates):
			deal_doc.save(ignore_permissions=True)
		return deal_doc.name

	new_doc_data: dict[str, object] = {
		"doctype": CRM_DEAL_DOCTYPE,
		"hubspot_deal_id": hubspot_deal_id,
	}
	new_doc_data.update(updates)

	deal_doc = frappe.get_doc(new_doc_data)
	deal_doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return deal_doc.name


def _build_crm_updates(*, event_data: dict[str, object], event_log: Document, deal_id: str) -> dict[str, object]:
	properties = _extract_hubspot_properties(event_data)

	updates: dict[str, object] = {}
	updates["hubspot_last_modified"] = _event_datetime(event_data)

	for property_name, property_value in properties.items():
		mapped_field, mapped_value = _map_property_to_crm_field(
			property_name=property_name,
			property_value=property_value,
		)
		if mapped_field:
			updates[mapped_field] = mapped_value

	if not properties and event_log.subscription_type == "deal.creation":
		fallback_field = _resolve_name_target_field()
		if fallback_field:
			updates.setdefault(fallback_field, f"HubSpot Deal {deal_id}")

	return {key: value for key, value in updates.items() if value is not None}


def _extract_hubspot_properties(event_data: dict[str, object]) -> dict[str, object]:
	properties: dict[str, object] = {}

	event_properties = event_data.get("properties")
	if isinstance(event_properties, dict):
		for key, value in event_properties.items():
			if isinstance(key, str):
				properties[key] = value

	return properties


def _build_event_data(event_log: Document) -> dict[str, object]:
	event_data: dict[str, object] = {
		"objectId": event_log.object_id,
		"subscriptionType": event_log.subscription_type,
	}

	occurred_at = event_log.occurred_at
	if occurred_at:
		event_data["occurredAt"] = occurred_at

	return event_data


def _event_datetime(event_data: dict[str, object]) -> datetime:
	occurred_at = event_data.get("occurredAt")
	if isinstance(occurred_at, datetime):
		if occurred_at.tzinfo is None:
			return occurred_at
		return occurred_at.astimezone(UTC).replace(tzinfo=None)

	parsed = _coerce_datetime(occurred_at)
	if parsed:
		return parsed

	return datetime.now(tz=UTC).replace(tzinfo=None)


def _apply_changed_fields(doc: Document, updates: dict[str, object]) -> bool:
	meta = frappe.get_meta(CRM_DEAL_DOCTYPE)
	changed = False
	for fieldname, value in updates.items():
		if not meta.has_field(fieldname):
			continue

		if doc.get(fieldname) != value:
			doc.set(fieldname, value)
			changed = True

	return changed


def _coerce_text(value: object) -> str | None:
	if value is None:
		return None

	text = str(value).strip()
	return text or None


def _coerce_float(value: object) -> float | None:
	if isinstance(value, bool) or value is None:
		return None

	if isinstance(value, int | float):
		return float(value)

	if isinstance(value, str):
		try:
			return float(value)
		except ValueError:
			return None

	return None


def _coerce_datetime(value: object) -> datetime | None:
	if isinstance(value, bool) or value is None:
		return None

	if isinstance(value, int | float):
		seconds = value / 1000 if value > 10**10 else value
		return datetime.fromtimestamp(seconds, tz=UTC).replace(tzinfo=None)

	if isinstance(value, str):
		stripped = value.strip()
		if not stripped:
			return None
		try:
			numeric = float(stripped)
		except ValueError:
			try:
				return datetime.fromisoformat(stripped.replace("Z", "+00:00")).astimezone(UTC).replace(
					tzinfo=None
				)
			except ValueError:
				return None

		seconds = numeric / 1000 if numeric > 10**10 else numeric
		return datetime.fromtimestamp(seconds, tz=UTC).replace(tzinfo=None)

	return None


def _coerce_date(value: object) -> str | None:
	parsed = _coerce_datetime(value)
	if parsed:
		return parsed.date().isoformat()

	if isinstance(value, str):
		candidate = value.strip()
		if len(candidate) >= 10:
			return candidate[:10]

	return None


def _map_property_to_crm_field(*, property_name: str, property_value: object) -> tuple[str | None, object | None]:
	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["name"]:
		target_field = _resolve_existing_field(("organization_name",))
		return target_field, _coerce_text(property_value)

	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["amount"]:
		target_field = _resolve_existing_field(("deal_value", "amount"))
		return target_field, _coerce_float(property_value)

	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["close_date"]:
		target_field = _resolve_existing_field(("expected_closure_date", "closed_date", "close_date"))
		return target_field, _coerce_date(property_value)

	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["stage_id"]:
		crm_status = _map_stage_to_crm_status(property_value)
		if crm_status:
			return "status", crm_status
		return None, None

	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["owner_id"]:
		target_field = _resolve_existing_field(("hubspot_owner_id",))
		return target_field, _coerce_text(property_value)

	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["pipeline_id"]:
		target_field = _resolve_existing_field(("hubspot_pipeline_id",))
		return target_field, _coerce_text(property_value)

	if property_name == HUBSPOT_DEAL_PROPERTY_KEYS["last_modified"]:
		target_field = _resolve_existing_field(("hubspot_last_modified",))
		return target_field, _coerce_datetime(property_value)

	return None, None


def _resolve_name_target_field() -> str | None:
	return _resolve_existing_field(("organization_name",))


def _resolve_existing_field(candidates: tuple[str, ...]) -> str | None:
	meta = frappe.get_meta(CRM_DEAL_DOCTYPE)
	for fieldname in candidates:
		if meta.has_field(fieldname):
			return fieldname

	return None


def _map_stage_to_crm_status(stage_value: object) -> str | None:
	stage_id = _coerce_text(stage_value)
	if not stage_id:
		return None

	if not frappe.db.exists("DocType", "HubSpot Stage Mapping"):
		return None

	crm_status = frappe.db.get_value(
		"HubSpot Stage Mapping",
		{"hubspot_stage_id": stage_id},
		"crm_deal_status",
	)

	if isinstance(crm_status, str) and crm_status:
		return crm_status

	return None
