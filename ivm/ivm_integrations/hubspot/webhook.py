"""
HubSpot webhook receiver.

Exposes ``handle_webhook`` that accepts incoming subscription events from
HubSpot, verifies the request signature, and enqueues the appropriate
handler for each event.

Supports the **generic webhook subscription** format (beta) where all
events use ``object.*`` subscription types (e.g. ``object.creation``,
``object.propertyChange``, ``object.associationChange``) and include an
``objectTypeId`` field to identify the object type.

Also retains backward-compatible support for the legacy subscription
format (e.g. ``deal.creation``, ``contact.propertyChange``) so that any
in-flight events from the old format are still handled.
"""

import json
import time
from typing import Any

import frappe
from ivm.ivm_integrations.hubspot import hubspot_client
from ivm.ivm_integrations.hubspot.constants import (
    BIN_TYPE_ID,
    CALL_TYPE_ID,
    COMPANY_TYPE_ID,
    CONTACT_TYPE_ID,
    DEAL_TYPE_ID,
    DEPLOYMENT_SITE_TYPE_ID,
    EMAIL_TYPE_ID,
    ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID,
    MACHINE_TYPE_TO_CHILD_TABLE,
    MEETING_TYPE_ID,
    NOTE_TYPE_ID,
    SMARTCENTER_TYPE_ID,
    SMARTLOCKER_TYPE_ID,
    SMARTSTATION_TYPE_ID,
    SMARTSYNC_TYPE_ID,
    SMARTVAULT_TYPE_ID,
    TASK_TYPE_ID,
)

# Maximum age (in seconds) for a webhook timestamp to be considered valid.
MAX_TIMESTAMP_AGE_SECONDS = 300

# ---------------------------------------------------------------------------
# Generic dispatch table: objectTypeId → (enqueue method, extra kwargs builder)
#
# Each value is a tuple of:
#   - Dotted path to the handler function (for frappe.enqueue)
#   - A callable that receives (object_id, event) and returns kwargs dict
# ---------------------------------------------------------------------------

_HANDLER_PREFIX = "ivm.ivm_integrations.hubspot"


def _deal_kwargs(object_id: str, event: dict) -> dict:
    return {"hubspot_deal_id": object_id}


def _contact_kwargs(object_id: str, event: dict) -> dict:
    return {"hubspot_contact_id": object_id}


def _company_kwargs(object_id: str, event: dict) -> dict:
    return {"hubspot_company_id": object_id}


def _site_kwargs(object_id: str, event: dict) -> dict:
    return {"hubspot_site_id": object_id}


def _machine_kwargs(object_id: str, event: dict) -> dict:
    return {
        "machine_type_id": str(event.get("objectTypeId", "")),
        "hubspot_machine_id": object_id,
    }


def _bin_kwargs(object_id: str, event: dict) -> dict:
    return {"hubspot_bin_id": object_id}


def _engagement_kwargs(object_id: str, event: dict) -> dict:
    object_type_id = str(event.get("objectTypeId", ""))
    engagement_type = ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID.get(object_type_id, "")
    return {
        "engagement_type": engagement_type,
        "engagement_id": object_id,
    }


# Maps objectTypeId → (handler method path, kwargs builder).
# For creation and propertyChange events, the "created" handler is used
# for creation and the "updated" handler for property changes.  Both are
# listed as (creation_handler, update_handler) tuples where they differ.
_OBJECT_TYPE_HANDLERS: dict[str, dict[str, tuple[str, Any]]] = {
    # --- Standard CRM objects ---
    DEAL_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_created", _deal_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_updated", _deal_kwargs),
        "object.associationChange": (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_updated", _deal_kwargs),
    },
    CONTACT_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_created", _contact_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_updated", _contact_kwargs),
        "object.associationChange": (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_updated", _contact_kwargs),
    },
    COMPANY_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.company_handler.handle_company_created", _company_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.company_handler.handle_company_updated", _company_kwargs),
        "object.associationChange": (f"{_HANDLER_PREFIX}.company_handler.handle_company_updated", _company_kwargs),
    },
    # --- Custom objects: deployment hierarchy ---
    DEPLOYMENT_SITE_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_site_webhook", _site_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_site_webhook", _site_kwargs),
    },
    BIN_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_bin_webhook", _bin_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_bin_webhook", _bin_kwargs),
    },
    # --- Engagement objects ---
    NOTE_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
    },
    CALL_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
    },
    EMAIL_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
    },
    TASK_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
    },
    MEETING_TYPE_ID: {
        "object.creation": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.activity_handler.handle_engagement_webhook", _engagement_kwargs),
    },
}

# Register all five machine types with the same handler
for _machine_type_id in MACHINE_TYPE_TO_CHILD_TABLE:
    _OBJECT_TYPE_HANDLERS[_machine_type_id] = {
        "object.creation": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_machine_webhook", _machine_kwargs),
        "object.propertyChange": (f"{_HANDLER_PREFIX}.deployment_site_handler.handle_machine_webhook", _machine_kwargs),
    }

# Legacy subscriptionType → (handler method path, kwarg name for object ID).
# Kept for backward compatibility with any in-flight events from the old format.
_LEGACY_DISPATCH: dict[str, tuple[str, str]] = {
    "deal.creation": (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_created", "hubspot_deal_id"),
    "deal.propertyChange": (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_updated", "hubspot_deal_id"),
    "deal.associationChange": (f"{_HANDLER_PREFIX}.deal_handler.handle_deal_updated", "hubspot_deal_id"),
    "company.creation": (f"{_HANDLER_PREFIX}.company_handler.handle_company_created", "hubspot_company_id"),
    "company.propertyChange": (f"{_HANDLER_PREFIX}.company_handler.handle_company_updated", "hubspot_company_id"),
    "company.associationChange": (f"{_HANDLER_PREFIX}.company_handler.handle_company_updated", "hubspot_company_id"),
    "contact.creation": (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_created", "hubspot_contact_id"),
    "contact.propertyChange": (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_updated", "hubspot_contact_id"),
    "contact.associationChange": (f"{_HANDLER_PREFIX}.contact_handler.handle_contact_updated", "hubspot_contact_id"),
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
            f"objectTypeId={event.get('objectTypeId')}, "
            f"objectId={event.get('objectId')}"
        )
        _route_event(event)

    return {"status": "ok"}


def _route_event(event: dict[str, Any]) -> None:
    """Route a single HubSpot subscription event to the appropriate handler.

    Supports two formats:
    - **Generic** (primary): ``subscriptionType`` like ``object.creation``
      with an ``objectTypeId`` field — routed via ``_OBJECT_TYPE_HANDLERS``.
    - **Legacy** (fallback): ``subscriptionType`` like ``deal.creation``
      — routed via ``_LEGACY_DISPATCH`` for backward compatibility.
    """

    subscription_type = event.get("subscriptionType", "")
    object_id = event.get("objectId")
    user_id = event.get("userId")

    if not object_id:
        return

    object_id_str = str(object_id)

    # --- Generic format (object.* with objectTypeId) ---
    if subscription_type.startswith("object."):
        object_type_id = str(event.get("objectTypeId", ""))
        type_handlers = _OBJECT_TYPE_HANDLERS.get(object_type_id)

        if type_handlers is None:
            frappe.logger("hubspot_webhook").warning(
                f"Unhandled objectTypeId: {object_type_id} "
                f"(subscriptionType={subscription_type})"
            )
            return

        handler_entry = type_handlers.get(subscription_type)
        if handler_entry is None:
            frappe.logger("hubspot_webhook").warning(
                f"No handler for {subscription_type} on objectTypeId {object_type_id}"
            )
            return

        method, kwargs_builder = handler_entry
        kwargs = kwargs_builder(object_id_str, event)
        kwargs["hubspot_user_id"] = user_id

        try:
            frappe.enqueue(method, queue="short", **kwargs)
        except Exception:
            frappe.log_error(
                title=f"HubSpot webhook: failed to enqueue {subscription_type} "
                      f"(objectTypeId={object_type_id}, objectId={object_id_str})",
                message=frappe.get_traceback(with_context=True),
            )
        return

    # --- Legacy format fallback (deal.creation, contact.propertyChange, etc.) ---
    handler = _LEGACY_DISPATCH.get(subscription_type)
    if handler is None:
        frappe.logger("hubspot_webhook").warning(
            f"Unhandled subscription type: {subscription_type} "
            f"(objectTypeId={event.get('objectTypeId')})"
        )
        return

    method, kwarg_name = handler
    try:
        frappe.enqueue(
            method,
            queue="short",
            hubspot_user_id=user_id,
            **{kwarg_name: object_id_str},
        )

    except Exception:
        frappe.log_error(
            title=f"HubSpot webhook: failed to enqueue {subscription_type}",
            message=frappe.get_traceback(with_context=True),
        )
