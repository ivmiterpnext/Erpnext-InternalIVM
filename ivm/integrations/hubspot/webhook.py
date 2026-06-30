"""HubSpot webhook receiver — verifies signatures and enqueues handlers."""

import json
import time
from typing import Any

import frappe
from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    BIN_TYPE_ID,
    COMPANY_TYPE_ID,
    CONTACT_TYPE_ID,
    DEAL_TYPE_ID,
    DEPLOYMENT_SITE_TYPE_ID,
    ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID,
    MACHINE_TYPE_TO_CHILD_TABLE,
)

MAX_TIMESTAMP_AGE_SECONDS = 300

_logger = frappe.logger("hubspot_webhook")
_HANDLER_PREFIX = "ivm.integrations.hubspot"


def _id_kwarg(key: str):
    """Return a kwargs builder that maps ``object_id`` to *key*."""
    def _builder(object_id: str, _event: dict) -> dict:
        return {key: object_id}
    return _builder


_deal_kwargs    = _id_kwarg("hubspot_deal_id")
_contact_kwargs = _id_kwarg("hubspot_contact_id")
_company_kwargs = _id_kwarg("hubspot_company_id")
_site_kwargs    = _id_kwarg("hubspot_site_id")
_bin_kwargs     = _id_kwarg("hubspot_bin_id")


def _machine_kwargs(object_id: str, event: dict) -> dict:
    return {
        "machine_type_id": str(event.get("objectTypeId", "")),
        "hubspot_machine_id": object_id,
    }


def _engagement_kwargs(object_id: str, event: dict) -> dict:
    object_type_id = str(event.get("objectTypeId", ""))
    return {
        "engagement_type": ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID.get(object_type_id, ""),
        "engagement_id": object_id,
    }


_OBJECT_TYPE_HANDLERS: dict[str, dict[str, tuple[str, Any]]] = {
    DEAL_TYPE_ID: {
        "object.creation":         (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_created", _deal_kwargs),
        "object.propertyChange":   (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_updated", _deal_kwargs),
        "object.associationChange":(f"{_HANDLER_PREFIX}.deal_handler.handle_deal_updated", _deal_kwargs),
    },
    CONTACT_TYPE_ID: {
        "object.creation":         (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_created", _contact_kwargs),
        "object.propertyChange":   (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_updated", _contact_kwargs),
        "object.associationChange":(f"{_HANDLER_PREFIX}.contact_handler.handle_contact_updated", _contact_kwargs),
    },
    COMPANY_TYPE_ID: {
        "object.creation":         (f"{_HANDLER_PREFIX}.company_handler.handle_company_created", _company_kwargs),
        "object.propertyChange":   (f"{_HANDLER_PREFIX}.company_handler.handle_company_updated", _company_kwargs),
        "object.associationChange":(f"{_HANDLER_PREFIX}.company_handler.handle_company_updated", _company_kwargs),
    },
    DEPLOYMENT_SITE_TYPE_ID: {
        "object.creation":       (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_site_webhook", _site_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_site_webhook", _site_kwargs),
    },
    BIN_TYPE_ID: {
        "object.creation":       (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_bin_webhook", _bin_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_bin_webhook", _bin_kwargs),
    },
}

for _machine_type_id in MACHINE_TYPE_TO_CHILD_TABLE:
    _OBJECT_TYPE_HANDLERS[_machine_type_id] = {
        "object.creation":       (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_machine_webhook", _machine_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_machine_webhook", _machine_kwargs),
    }

for _engagement_type_id in ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID:
    _OBJECT_TYPE_HANDLERS[_engagement_type_id] = {
        "object.creation":       (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
    }


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


@frappe.whitelist(allow_guest=True, methods=["POST"])
def handle_webhook() -> dict[str, str]:
    """Verify signature and enqueue a handler for each incoming HubSpot event."""
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
        _logger.info(
            f"Received event: subscriptionType={event.get('subscriptionType')}, "
            f"objectTypeId={event.get('objectTypeId')}, "
            f"objectId={event.get('objectId')}"
        )
        _route_event(event)

    return {"status": "ok"}


def _route_event(event: dict[str, Any]) -> None:
    """Route a single event to its handler."""
    subscription_type = event.get("subscriptionType", "")
    object_id = event.get("objectId")
    user_id = event.get("userId")

    if not object_id:
        return

    object_id_str = str(object_id)
    object_type_id = str(event.get("objectTypeId", ""))
    type_handlers = _OBJECT_TYPE_HANDLERS.get(object_type_id)

    if type_handlers is None:
        _logger.warning(f"Unhandled objectTypeId: {object_type_id} (subscriptionType={subscription_type})")
        return

    handler_entry = type_handlers.get(subscription_type)
    if handler_entry is None:
        _logger.warning(f"No handler for {subscription_type} on objectTypeId {object_type_id}")
        return

    method, kwargs_builder = handler_entry
    kwargs = kwargs_builder(object_id_str, event)
    kwargs["hubspot_user_id"] = user_id

    try:
        frappe.enqueue(method, queue="long", **kwargs)
    except Exception:
        frappe.log_error(
            title=f"HubSpot webhook: failed to enqueue {subscription_type} "
                  f"(objectTypeId={object_type_id}, objectId={object_id_str})",
            message=frappe.get_traceback(with_context=True),
        )
