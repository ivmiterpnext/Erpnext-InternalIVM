import json
import time
from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client, deal_handler

# Maximum age (in seconds) for a webhook timestamp to be considered valid.
MAX_TIMESTAMP_AGE_SECONDS = 300


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_webhook() -> dict[str, str]:
	"""HubSpot webhook endpoint.

	Receives an array of subscription events from HubSpot, verifies the
	request signature, and enqueues the appropriate handler for each event.

	Returns 200 immediately so HubSpot does not retry.
	"""
	request = frappe.request
	request_body = request.get_data(as_text=True)

	# --- Signature verification ---
	signature = request.headers.get("X-HubSpot-Signature", "")
	timestamp = request.headers.get("X-HubSpot-Request-Timestamp", "")

	# Reject stale requests
	try:
		ts = int(timestamp)
		if abs(time.time() * 1000 - ts) > MAX_TIMESTAMP_AGE_SECONDS * 1000:
			frappe.throw("Webhook timestamp too old", frappe.AuthenticationError)
	except (ValueError, TypeError):
		frappe.throw("Invalid webhook timestamp", frappe.AuthenticationError)

	if not hubspot_client.verify_signature(request_body, signature):
		frappe.throw("Invalid webhook signature", frappe.AuthenticationError)


	# --- Process events ---
	try:
		events: list[dict[str, Any]] = json.loads(request_body)
	except (json.JSONDecodeError, TypeError):
		frappe.log_error(
			title="HubSpot webhook: invalid JSON payload",
			message=request_body[:2000],
		)
		return {"status": "error", "message": "Invalid JSON payload"}

	for event in events:
		_route_event(event)

	return {"status": "ok"}


def _route_event(event: dict[str, Any]) -> None:
	"""Route a single HubSpot subscription event to the appropriate handler."""
	subscription_type = event.get("subscriptionType", "")
	object_id = event.get("objectId")

	if not object_id:
		return

	if subscription_type == "deal.creation":
		# deal_handler.handle_deal_created(object_id)
		try:
			frappe.enqueue(
				"ivm.ivm_integrations.hubspot.deal_handler.handle_deal_created",
				queue="short",
				hubspot_deal_id=object_id,
			)
		except Exception:
			frappe.log_error(
				title="HubSpot webhook: failed to enqueue deal.creation",
				message=frappe.get_traceback(with_context=True),
			)
	elif subscription_type == "deal.propertyChange":
		property_name = event.get("propertyName", "")
		property_value = event.get("propertyValue", "")

		if property_name == "dealstage" and property_value == "2508204768":
			deal_handler.handle_deal_closed_won(object_id)
			# try:
			# 	frappe.enqueue(
			# 		"ivm.ivm_integrations.hubspot.deal_handler.handle_deal_closed_won",
			# 		queue="short",
			# 		hubspot_deal_id=object_id,
			# 	)
			# except Exception:
			# 	frappe.log_error(
			# 		title="HubSpot webhook: failed to enqueue deal closedwon",
			# 		message=frappe.get_traceback(with_context=True),
			# 	)
