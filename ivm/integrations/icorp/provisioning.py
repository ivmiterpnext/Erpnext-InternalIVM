"""
Create iCorp contacts and clients from Frappe records.

Shared by the Customer form's "Create new in iCorp" action
(ivm.machine_hardware_management.doctype.icorp_client_link.create_icorp_client_for_customer).

The *_with_error helpers return (new iCorp id, None) on success, or (None, error text)
on any failure (error response, missing id, or exception), so the caller can show the
user why. Failures are logged via log_icorp_error (survives the request rollback that
follows the caller's frappe.throw).
"""

from __future__ import annotations

from typing import Any

import frappe

from ivm.integrations.icorp.api import extract_id, icorp_api_post

_LOG = "ivm.integrations.icorp.provisioning"
_ERROR_TEXT_MAX_CHARS = 500


def get_primary_value(
	rows: list[Any],
	value_field: str,
	primary_field: str = "is_primary",
) -> str:
	"""Return the primary row's value, falling back to the first row."""
	for row in rows:
		if row.get(primary_field):
			return row.get(value_field) or ""
	return rows[0].get(value_field) or "" if rows else ""


def get_contact_phone(contact_doc: Any) -> str:
	"""The phone iCorp receives for a Frappe Contact, or "" when there is none.

	Order: primary `phone_nos` row, then the first `phone_nos` row with a number,
	then the legacy `mobile_no` and `phone` fields.
	"""
	rows = [row for row in (contact_doc.get("phone_nos") or []) if (row.get("phone") or "").strip()]
	primary = next((row for row in rows if row.get("is_primary_phone")), None)
	chosen = primary or (rows[0] if rows else None)
	if chosen:
		return chosen.get("phone").strip()
	for field in ("mobile_no", "phone"):
		value = (contact_doc.get(field) or "").strip()
		if value:
			return value
	return ""


def icorp_error_text(response: dict[str, Any]) -> str:
	"""Readable text from an error dict returned by icorp_api_post.

	Prefers the raw response body (iCorp's plain-text validation messages, e.g.
	"Must have a least 1 contact phone number."), stripped and truncated. Falls back
	to response["error"]. Appends the HTTP status when present.
	"""
	text = str(response.get("text") or "").strip()
	if len(text) > _ERROR_TEXT_MAX_CHARS:
		text = text[:_ERROR_TEXT_MAX_CHARS].rstrip() + "..."
	message = text or str(response.get("error") or "Unknown iCorp error")
	status = response.get("status_code")
	return f"{message} (HTTP {status})" if status is not None else message


def log_icorp_error(title: str, message: str) -> None:
	"""Error Log entry that survives the caller's rollback.

	Not defer_insert: that pushes to Redis for the 15-minute save_to_db cron
	(frappe/deferred_insert.py) and only logs insert failures to frappe.log, so the
	row is neither immediate nor reliable. Insert now. `tabError Log` is MyISAM
	(non-transactional), so a later frappe.throw rollback does not remove it. If a
	transactional engine ever rolls it back, after_rollback re-creates it and commits.
	"""
	error_log = frappe.log_error(title=title, message=message)
	name = error_log.name
	frappe.db.after_rollback.add(lambda: _ensure_error_log(name, title, message))


def _ensure_error_log(name: str, title: str, message: str) -> None:
	"""Re-create the Error Log row if a rollback removed it, then commit."""
	if frappe.db.exists("Error Log", name):
		return
	frappe.log_error(title=title, message=message)
	frappe.db.commit()


def build_contact_payload(contact_doc: Any) -> dict[str, Any]:
	"""iCorp Contact POST payload built from a Frappe Contact."""
	email = get_primary_value(contact_doc.get("email_ids") or [], "email_id")
	return {
		"first_name": contact_doc.first_name or "",
		"middle_name": contact_doc.middle_name or "",
		"last_name": contact_doc.last_name or "",
		"email_address": email,
		"phone1": get_contact_phone(contact_doc),
		"phone_type_id1": 1,
		"title": contact_doc.designation or "",
	}


def create_icorp_contact_with_error(contact_doc: Any) -> tuple[int | None, str | None]:
	"""Create a contact in iCorp from a Frappe Contact. Returns (contact_id, None) on success,
	or (None, error_text) on failure, so callers can show the user why."""
	payload = build_contact_payload(contact_doc)

	try:
		response = icorp_api_post("Contact", payload)

		if isinstance(response, dict) and response.get("error"):
			log_icorp_error(
				"iCorp: failed to create contact",
				f"Frappe Contact {contact_doc.name}\nPayload: {payload}\nResponse: {response}",
			)
			return None, icorp_error_text(response)

		icorp_contact_id = extract_id(response, "contact")
		if icorp_contact_id is None:
			log_icorp_error(
				"iCorp: contact created but no id returned",
				f"Frappe Contact {contact_doc.name}\nResponse: {response}",
			)
			return None, f"iCorp returned no contact id. Response: {response}"
		return icorp_contact_id, None

	except Exception as e:
		log_icorp_error("iCorp: failed to create contact", frappe.get_traceback(with_context=True))
		return None, str(e)


def create_icorp_client_with_error(
	client_name: str,
	icorp_contact_id: int,
	partner_client_id: int | None = None,
) -> tuple[int | None, str | None]:
	"""Create a client in iCorp, returning (client_id, None) on success or (None, error_text)
	on failure, where error_text is iCorp's own message when available.

	partner_client_id, when given, is sent as the client's iCorp parent
	(`partner_client_id` in snake_case here; icorp_api_post converts it to
	`partnerClientId` on the wire, the same convention as `primary_contact_id`).
	"""
	payload: dict[str, Any] = {
		"name": client_name,
		"is_active": True,
		"is_enhanced_client": False,
		"using_enhanced_assignments": False,
		"restriction_priority_type_id": 2,
		"primary_contact_id": icorp_contact_id,
		"check_frequency_type_code": "M",
		"fee_rate_id": 1,
	}
	if partner_client_id:
		payload["partner_client_id"] = int(partner_client_id)

	try:
		response = icorp_api_post("Client", payload)

		if isinstance(response, dict) and response.get("error"):
			log_icorp_error(
				f"iCorp: failed to create client '{client_name}'",
				f"Payload: {payload}\nResponse: {response}",
			)
			return None, icorp_error_text(response)

		icorp_client_id = extract_id(response, "client")
		if icorp_client_id is None:
			log_icorp_error(
				f"iCorp: client '{client_name}' created but no id returned",
				f"Payload: {payload}\nResponse: {response}",
			)
			return None, f"iCorp returned no client id. Response: {response}"
		return icorp_client_id, None

	except Exception as e:
		log_icorp_error(
			f"iCorp: failed to create client '{client_name}'",
			frappe.get_traceback(with_context=True),
		)
		return None, str(e)
