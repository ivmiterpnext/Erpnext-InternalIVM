"""HubSpot webhook receiver — verifies signatures and enqueues handlers."""

import json
import time
from typing import Any

import frappe

from ivm.integrations.hubspot import api, routing

MAX_TIMESTAMP_AGE_SECONDS = 300
DEV_RELAY_TIMEOUT_SECONDS = 5

_logger = frappe.logger("hubspot_webhook")


def _verify_request(body: str, signature: str, timestamp: str) -> None:
	"""Raise AuthenticationError if the request is stale or has an invalid signature."""
	try:
		ts = int(timestamp)
		if abs(time.time() * 1000 - ts) > MAX_TIMESTAMP_AGE_SECONDS * 1000:
			frappe.throw("Webhook timestamp too old", frappe.AuthenticationError)
	except (ValueError, TypeError):
		frappe.throw("Invalid webhook timestamp", frappe.AuthenticationError)

	if not api.verify_signature(body, signature):
		frappe.throw("Invalid webhook signature", frappe.AuthenticationError)


_ROUTABLE_SUBSCRIPTION_TYPES = frozenset(
	{"object.creation", "object.propertyChange", "object.associationChange"}
)


def _route_event(event: dict[str, Any]) -> str:
	"""Route a single event through routing.route(). Returns the routing
	outcome string: "enqueued", "skipped", "dropped", "unhandled", or
	"ignored" (not a routable subscription type — e.g. object.deletion,
	object.merge, object.restore, none of which have a Frappe-side handler).
	"""
	subscription_type = event.get("subscriptionType", "")
	if subscription_type not in _ROUTABLE_SUBSCRIPTION_TYPES:
		return "ignored"

	if subscription_type == "object.associationChange":
		results = []
		from_type = str(event.get("fromObjectTypeId", ""))
		from_id = event.get("fromObjectId")
		to_type = str(event.get("toObjectTypeId", ""))
		to_id = event.get("toObjectId")

		if from_id:
			results.append(routing.route(from_type, str(from_id)))
		if to_id:
			results.append(routing.route(to_type, str(to_id)))

		if not results:
			return "ignored"
		# Prefer reporting "enqueued" if either side enqueued; otherwise report the first outcome.
		return "enqueued" if "enqueued" in results else results[0]

	object_id = event.get("objectId")
	if not object_id:
		return "ignored"

	object_type_id = str(event.get("objectTypeId", ""))
	return routing.route(object_type_id, str(object_id))


def _forward_to_dev(body: str, signature: str, timestamp: str, content_type: str) -> None:
	"""Best-effort forward of the raw HubSpot payload to a dev tunnel. No-op if unconfigured. Never raises."""
	relay_url = frappe.conf.get("hubspot_dev_relay_url")
	if not relay_url:
		return
	try:
		import requests

		requests.post(
			relay_url,
			data=body.encode("utf-8"),
			headers={
				"Content-Type": content_type,
				"X-HubSpot-Signature": signature,
				"X-HubSpot-Request-Timestamp": timestamp,
				"ngrok-skip-browser-warning": "true",
			},
			timeout=DEV_RELAY_TIMEOUT_SECONDS,
		)
	except Exception:
		_logger.warning(f"hubspot dev relay forward failed: {frappe.get_traceback()}")


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_webhook() -> dict[str, Any]:
	"""Verify signature and enqueue a handler for each incoming HubSpot event."""
	request = frappe.request
	request_body = request.get_data(as_text=True)

	_verify_request(
		body=request_body,
		signature=request.headers.get("X-HubSpot-Signature", ""),
		timestamp=request.headers.get("X-HubSpot-Request-Timestamp", ""),
	)

	if frappe.conf.get("hubspot_dev_relay_url"):
		frappe.enqueue(
			_forward_to_dev,
			queue="short",
			body=request_body,
			signature=request.headers.get("X-HubSpot-Signature", ""),
			timestamp=request.headers.get("X-HubSpot-Request-Timestamp", ""),
			content_type=request.headers.get("Content-Type", "application/json"),
		)

	try:
		events: list[dict[str, Any]] = json.loads(request_body)
	except (json.JSONDecodeError, TypeError):
		frappe.log_error(
			title="HubSpot webhook: invalid JSON payload",
			message=request_body[:2000],
		)
		return {"status": "error", "message": "Invalid JSON payload"}

	results: dict[str, int] = {}
	for event in events:
		_logger.info(
			f"Received event: subscriptionType={event.get('subscriptionType')}, "
			f"objectTypeId={event.get('objectTypeId')}, "
			f"objectId={event.get('objectId')}"
		)
		try:
			outcome = _route_event(event)
		except Exception:
			frappe.log_error(
				title="HubSpot webhook: failed to route event",
				message=f"event={event}\n\n{frappe.get_traceback(with_context=True)}",
			)
			outcome = "failed"
		results[outcome] = results.get(outcome, 0) + 1

	if results.get("failed"):
		_logger.warning(f"HubSpot webhook batch results: {results}")

	return {"status": "ok", "results": results}
