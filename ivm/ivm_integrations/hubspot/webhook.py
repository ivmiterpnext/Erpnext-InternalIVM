"""
HubSpot webhook receiver.

Exposes `handle_webhook` that accepts incoming
subscription events from HubSpot, verifies the request signature, and
enqueues the appropriate handler for each event via a dispatch table.
"""

import json
import time
from typing import Any
import frappe
from ivm.ivm_integrations.hubspot import hubspot_client

# Maximum age (in seconds) for a webhook timestamp to be considered valid.
MAX_TIMESTAMP_AGE_SECONDS = 300

# Maps HubSpot subscriptionType → (enqueue method path, keyword arg name).
_EVENT_DISPATCH: dict[str, tuple[str, str]] = {
    "deal.creation": ("ivm.ivm_integrations.hubspot.deal_handler.handle_deal_created", "hubspot_deal_id"),
    "deal.propertyChange": ("ivm.ivm_integrations.hubspot.deal_handler.handle_deal_updated", "hubspot_deal_id"),
    "deal.associationChange": ("ivm.ivm_integrations.hubspot.deal_handler.handle_deal_updated", "hubspot_deal_id"),
    "company.creation": ("ivm.ivm_integrations.hubspot.company_handler.handle_company_created", "hubspot_company_id"),
    "company.propertyChange": ("ivm.ivm_integrations.hubspot.company_handler.handle_company_updated", "hubspot_company_id"),
    "company.associationChange": ("ivm.ivm_integrations.hubspot.company_handler.handle_company_updated", "hubspot_company_id"),
    "contact.creation": ("ivm.ivm_integrations.hubspot.contact_handler.handle_contact_created", "hubspot_contact_id"),
    "contact.propertyChange": ("ivm.ivm_integrations.hubspot.contact_handler.handle_contact_updated", "hubspot_contact_id"),
    "contact.associationChange": ("ivm.ivm_integrations.hubspot.contact_handler.handle_contact_updated", "hubspot_contact_id"),
}


def _verify_request(body: str, signature: str, timestamp: str) -> None:
    """Raise AuthenticationError if the request is stale or has an invalid signature."""

    try:
        ts = int(timestamp)
        if abs(time.time() * 1000 - ts) > MAX_TIMESTAMP_AGE_SECONDS * 1000:
            frappe.throw("Webhook timestamp too old", frappe.AuthenticationError)

    except (ValueError, TypeError):
        frappe.throw("Invalid webhook timestamp", frappe.AuthenticationError)

    if not hubspot_client.verify_signature(body, signature):
        frappe.throw("Invalid webhook signature", frappe.AuthenticationError)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_webhook() -> dict[str, str]:
    """
    Receives an array of subscription events from HubSpot, 
    verifies the request signature, and enqueues the appropriate handler for each event.

    Returns 200 immediately so HubSpot does not retry.
    """

    request = frappe.request
    request_body = request.get_data(as_text=True)

    _verify_request(
        body=request_body,
        signature=request.headers.get("X-HubSpot-Signature", ""),
        timestamp=request.headers.get("X-HubSpot-Request-Timestamp", ""),
    )

    try:
        events: list[dict[str, Any]] = json.loads(request_body)

    except (json.JSONDecodeError, TypeError):
        frappe.log_error(
            title="HubSpot webhook: invalid JSON payload",
            message=request_body[:2000],
        )
        return {"status": "error", "message": "Invalid JSON payload"}

    for event in events:
        frappe.logger("hubspot_webhook").info(
            f"Received event: subscriptionType={event.get('subscriptionType')}, "
            f"objectId={event.get('objectId')}"
        )
        _route_event(event)

    return {"status": "ok"}


def _route_event(event: dict[str, Any]) -> None:
    """Route a single HubSpot subscription event to the appropriate handler."""

    subscription_type = event.get("subscriptionType", "")
    object_id = event.get("objectId")

    if not object_id:
        return

    handler = _EVENT_DISPATCH.get(subscription_type)
    if handler is None:
        frappe.logger("hubspot_webhook").warning(
            f"Unhandled subscription type: {subscription_type}"
        )
        return

    method, kwarg_name = handler
    try:
        frappe.enqueue(method, queue="short", **{kwarg_name: object_id})

    except Exception:
        frappe.log_error(
            title=f"HubSpot webhook: failed to enqueue {subscription_type}",
            message=frappe.get_traceback(with_context=True),
        )
