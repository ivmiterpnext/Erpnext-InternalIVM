"""HubSpot webhook endpoint and async event processing."""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import b64encode
from datetime import UTC, datetime
from typing import Final

import frappe
from frappe.exceptions import DuplicateEntryError

from ivm.ivm_integrations.hubspot.constants import (
	HUBSPOT_EVENT_SUBSCRIPTION_TYPES,
	HUBSPOT_WEBHOOK_SIGNATURE_HEADER,
	HUBSPOT_WEBHOOK_TIMESTAMP_HEADER,
	WEBHOOK_ALLOWED_TIMESTAMP_SKEW_SECONDS,
)

HUBSPOT_SETTINGS_DOCTYPE: Final[str] = "HubSpot Settings"
WEBHOOK_EVENT_DOCTYPE: Final[str] = "HubSpot Webhook Event"


@frappe.whitelist(allow_guest=True)
def handle() -> dict[str, int | str]:
	"""Receive HubSpot webhooks, validate authenticity, and enqueue processing."""
	settings = _get_hubspot_settings()
	if not settings.get("enabled"):
		return {"status": "ignored", "reason": "disabled", "queued": 0, "ignored": 0}

	request_body = frappe.request.get_data(as_text=True) or ""
	_validate_webhook_signature(
		request_body=request_body,
		secret=str(settings.get("webhook_secret") or ""),
	)

	events = _parse_events(request_body)
	queued = 0
	ignored = 0

	for event in events:
		if not _is_supported_deal_event(event):
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
	"""Worker entry point for syncing a deal event."""
	event_log = frappe.get_doc(WEBHOOK_EVENT_DOCTYPE, event_log_name)
	if event_log.status == "Processed":
		return

	event_log.db_set("status", "Queued")

	try:
		from ivm.ivm_integrations.hubspot.service import sync_deal_from_event_log

		sync_deal_from_event_log(event_log_name=event_log_name)
		event_log.db_set("status", "Processed")
	except Exception:
		frappe.log_error(
			title="HubSpot deal event processing failed",
			message=frappe.get_traceback(with_context=True),
		)
		event_log.db_set("status", "Failed")
		raise


def _get_hubspot_settings() -> dict[str, object]:
	return frappe.get_cached_value(
		HUBSPOT_SETTINGS_DOCTYPE,
		HUBSPOT_SETTINGS_DOCTYPE,
		["enabled", "webhook_secret"],
		as_dict=True,
	) or {}


def _validate_webhook_signature(*, request_body: str, secret: str) -> None:
	if not secret:
		raise frappe.PermissionError("HubSpot webhook secret is not configured.")

	timestamp_header = frappe.get_request_header(HUBSPOT_WEBHOOK_TIMESTAMP_HEADER) or ""
	signature_header = frappe.get_request_header(HUBSPOT_WEBHOOK_SIGNATURE_HEADER) or ""

	if not timestamp_header or not signature_header:
		raise frappe.PermissionError("Missing HubSpot signature headers.")

	if _is_stale_timestamp(timestamp_header):
		raise frappe.PermissionError("HubSpot webhook timestamp is stale.")

	request_method = (frappe.request.method or "").upper()
	request_uri = frappe.request.url or ""
	body_for_signature = _stringify_request_body(request_body)
	source = f"{request_method}{request_uri}{body_for_signature}{timestamp_header}".encode("utf-8")
	hmac_bytes = hmac.new(secret.encode("utf-8"), source, hashlib.sha256).digest()
	computed = b64encode(hmac_bytes).decode("utf-8")

	if not hmac.compare_digest(computed, signature_header):
		raise frappe.PermissionError("Invalid HubSpot webhook signature.")


def _stringify_request_body(request_body: str) -> str:
	try:
		body_obj = json.loads(request_body or "[]")
	except json.JSONDecodeError:
		return request_body

	return json.dumps(body_obj, separators=(",", ":"), ensure_ascii=False)


def _is_stale_timestamp(timestamp_header: str) -> bool:
	try:
		timestamp_value = int(timestamp_header)
	except (TypeError, ValueError):
		return True

	if timestamp_value > 10**10:
		timestamp_seconds = timestamp_value / 1000
	else:
		timestamp_seconds = timestamp_value

	now_seconds = datetime.now(tz=UTC).timestamp()
	return abs(now_seconds - timestamp_seconds) > WEBHOOK_ALLOWED_TIMESTAMP_SKEW_SECONDS


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


def _is_supported_deal_event(event: dict[str, object]) -> bool:
	subscription_type = str(event.get("subscriptionType") or "")
	object_id = event.get("objectId")

	if not object_id:
		return False

	return subscription_type in HUBSPOT_EVENT_SUBSCRIPTION_TYPES


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


def _coerce_text(value: object) -> str | None:
	if value is None:
		return None

	text = str(value).strip()
	return text or None
