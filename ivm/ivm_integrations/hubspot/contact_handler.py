"""HubSpot Contact → Frappe Contact sync handler.

Handles both:
- **Standalone webhooks** (``contact.creation`` / ``contact.propertyChange``)
  that upsert a Frappe Contact directly.
- **Deal-association sync** via the public ``upsert_contact()`` helper,
  which ``deal_handler._ensure_contacts`` delegates to so that contact
  creation logic lives in one place.

Contact is more complex than Company or Deal because the primary email
and phone numbers live in child tables (``Contact Email`` /
``Contact Phone``), not flat fields.  The ``CONTACT_FIELD_MAP`` in
constants maps HubSpot properties to intermediate dict keys; the actual
doc manipulation happens in ``upsert_contact()``.
"""

from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client
from ivm.ivm_integrations.hubspot.constants import CONTACT_FIELD_MAP
from ivm.ivm_integrations.hubspot.sync_utils import (
    save_doc,
    set_hubspot_user,
)

# HubSpot ID field on Contact.  Must be added as a Custom Field
# (custom_hubspot_contact_id) on the Contact DocType before the
# standalone webhook handlers will work.  The deal-association path
# (upsert_contact) can still fall back to email-based de-duplication.
HUBSPOT_ID_FIELD = "custom_hubspot_contact_id"


# ---------------------------------------------------------------------------
# Public entry points (called from webhook.py via frappe.enqueue)
# ---------------------------------------------------------------------------


def handle_contact_created(hubspot_contact_id: int | str) -> None:
    """Create a Frappe Contact from a newly created HubSpot contact."""
    set_hubspot_user()
    try:
        props = _fetch_contact_properties(hubspot_contact_id)
        if props is None:
            return
        upsert_contact(props, hubspot_contact_id=str(hubspot_contact_id))
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to create Contact for HubSpot contact {hubspot_contact_id}",
            message=frappe.get_traceback(with_context=True),
        )


def handle_contact_updated(hubspot_contact_id: int | str) -> None:
    """Sync a HubSpot contact's current state to the matching Frappe Contact."""
    set_hubspot_user()
    try:
        props = _fetch_contact_properties(hubspot_contact_id)
        if props is None:
            return
        upsert_contact(props, hubspot_contact_id=str(hubspot_contact_id))
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync contact {hubspot_contact_id}",
            message=frappe.get_traceback(with_context=True),
        )


# ---------------------------------------------------------------------------
# Shared upsert logic (used by both webhook handlers and deal_handler)
# ---------------------------------------------------------------------------


def upsert_contact(
    properties: dict[str, Any],
    hubspot_contact_id: str | None = None,
) -> str | None:
    """Create or update a Frappe Contact from a mapped property dict.

    Parameters
    ----------
    properties:
        Dict with keys matching the *values* side of ``CONTACT_FIELD_MAP``
        (``first_name``, ``last_name``, ``email``, ``mobile_no``, ``phone``,
        ``company_name``).
    hubspot_contact_id:
        If provided, used to look up / stamp the Contact via
        ``custom_hubspot_contact_id``.  When called from the deal
        association path this may be ``None``, in which case we fall back
        to email-based de-duplication.

    Returns
    -------
    str | None:
        The Frappe Contact ``name``, or ``None`` if the contact could not
        be created (missing both name and email).
    """
    email = (properties.get("email") or "").strip()
    first_name = (properties.get("first_name") or "").strip()
    last_name = (properties.get("last_name") or "").strip()

    if not first_name and not email:
        return None

    contact_doc = _find_existing_contact(email, hubspot_contact_id)

    if contact_doc:
        _update_contact_fields(contact_doc, first_name, last_name, properties)
        _sync_email(contact_doc, email)
        _sync_phone_numbers(contact_doc, properties)
        _set_hubspot_id(contact_doc, hubspot_contact_id)
        save_doc(contact_doc, "contact")
    else:
        contact_doc = frappe.new_doc("Contact")
        contact_doc.first_name = first_name or email
        contact_doc.last_name = last_name
        contact_doc.company_name = properties.get("company_name") or ""
        _set_hubspot_id(contact_doc, hubspot_contact_id)

        if email:
            contact_doc.append("email_ids", {"email_id": email, "is_primary": 1})

        mobile_no = (properties.get("mobile_no") or "").strip()
        if mobile_no:
            contact_doc.append("phone_nos", {"phone": mobile_no, "is_primary_mobile_no": 1})

        phone = (properties.get("phone") or "").strip()
        if phone:
            contact_doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1})

        contact_doc.insert(ignore_permissions=True)
        frappe.db.commit()
        frappe.logger("hubspot").info(
            f"Created Contact {contact_doc.name} ({first_name} {last_name})"
        )

    return contact_doc.name


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_contact_properties(hubspot_contact_id: int | str) -> dict[str, Any] | None:
    """Fetch a HubSpot contact and return a mapped property dict.

    Returns ``None`` on failure (already logged).
    """
    try:
        hs_properties = list(CONTACT_FIELD_MAP.keys())
        contact_data = hubspot_client.get_contact(
            hubspot_contact_id, properties=hs_properties,
        )
        raw_props = contact_data.get("properties", {})
        return {
            frappe_key: raw_props.get(hs_key) or ""
            for hs_key, frappe_key in CONTACT_FIELD_MAP.items()
        }
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch contact {hubspot_contact_id}",
            message=frappe.get_traceback(with_context=True),
        )
        return None


def _find_existing_contact(
    email: str,
    hubspot_contact_id: str | None,
) -> Any | None:
    """Look up an existing Frappe Contact by HubSpot ID or email.

    HubSpot ID takes precedence when available.
    """
    if hubspot_contact_id:
        name = frappe.db.get_value(
            "Contact", {HUBSPOT_ID_FIELD: hubspot_contact_id}, "name",
        )
        if name:
            return frappe.get_doc("Contact", name)

    if email:
        name = frappe.db.get_value("Contact", {"email_id": email}, "name")
        if name:
            return frappe.get_doc("Contact", name)

    return None


def _update_contact_fields(
    doc: Any,
    first_name: str,
    last_name: str,
    properties: dict[str, Any],
) -> None:
    """Update flat fields on an existing Contact doc."""
    if first_name:
        doc.first_name = first_name
    if last_name:
        doc.last_name = last_name
    company_name = (properties.get("company_name") or "").strip()
    if company_name:
        doc.company_name = company_name


def _sync_email(doc: Any, email: str) -> None:
    """Ensure the primary email is present in the email_ids child table."""
    if not email:
        return

    existing_emails = {row.email_id for row in (doc.get("email_ids") or [])}
    if email not in existing_emails:
        # Clear old primary flags and add the new email as primary
        for row in doc.get("email_ids") or []:
            row.is_primary = 0
        doc.append("email_ids", {"email_id": email, "is_primary": 1})


def _sync_phone_numbers(doc: Any, properties: dict[str, Any]) -> None:
    """Ensure mobile and phone numbers are present in the phone_nos child table."""
    existing_phones = {row.phone for row in (doc.get("phone_nos") or [])}

    mobile_no = (properties.get("mobile_no") or "").strip()
    if mobile_no and mobile_no not in existing_phones:
        doc.append("phone_nos", {"phone": mobile_no, "is_primary_mobile_no": 1})

    phone = (properties.get("phone") or "").strip()
    if phone and phone not in existing_phones:
        doc.append("phone_nos", {"phone": phone, "is_primary_phone": 1})


def _set_hubspot_id(doc: Any, hubspot_contact_id: str | None) -> None:
    """Stamp the HubSpot contact ID on the doc if the field exists."""
    if not hubspot_contact_id:
        return
    meta = frappe.get_meta("Contact")
    if meta.get_field(HUBSPOT_ID_FIELD):
        doc.set(HUBSPOT_ID_FIELD, hubspot_contact_id)
