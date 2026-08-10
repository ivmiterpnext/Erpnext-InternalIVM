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

import re
from typing import Any

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    CONTACT_ADDRESS_PROPERTIES,
    CONTACT_FIELD_MAP,
    HUBSPOT_CONTACT_ID_FIELD,
)
from ivm.integrations.hubspot.sync_utils import (
    save_doc,
    set_acting_user,
    upsert_address,
)

HUBSPOT_ID_FIELD = HUBSPOT_CONTACT_ID_FIELD

_EXT_PATTERN = re.compile(r"\s*(?:ext\.?|x)\s*(\d+)\s*$", re.IGNORECASE)
_PHONE_CHARS = re.compile(r"[^0-9 +_\-,.*#()]")


def _sanitize_phone(raw: str) -> tuple[str, str]:
    """Strip extension suffixes from a phone number.

    Returns ``(phone, extension)`` where *extension* is the bare digit
    string (e.g. ``"1254"``) or ``""`` if none was found.
    """
    raw = (raw or "").strip()
    if not raw:
        return ("", "")

    extension = ""
    m = _EXT_PATTERN.search(raw)
    if m:
        extension = m.group(1)
        raw = raw[:m.start()].strip()

    # Strip any remaining non-phone characters (letters, etc.)
    raw = _PHONE_CHARS.sub("", raw).strip()

    # Frappe's phone regex allows max 20 characters
    if len(raw) > 20:
        raw = raw[:20].strip()

    if not raw:
        return ("", "")

    return (raw, extension)


# Fields from the field map that are handled specially (child tables, etc.)
# rather than being set directly as flat fields on the Contact doc.
_CHILD_TABLE_KEYS = frozenset({"email", "mobile_no", "phone"})

_SKIP_FLAT_KEYS = _CHILD_TABLE_KEYS | {"first_name", "last_name"}


def handle_contact_created(
    hubspot_contact_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Create a Frappe Contact from a newly created HubSpot contact."""
    _handle_contact_event(hubspot_contact_id, hubspot_user_id, "create")


def handle_contact_updated(
    hubspot_contact_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Sync a HubSpot contact's current state to the matching Frappe Contact."""
    _handle_contact_event(hubspot_contact_id, hubspot_user_id, "sync")


def _handle_contact_event(
    hubspot_contact_id: int | str,
    hubspot_user_id: int | str | None,
    action: str,
) -> None:
    """Shared handler for contact creation and update webhooks."""
    set_acting_user(hubspot_user_id)
    try:
        props, address_props = _fetch_contact_properties(hubspot_contact_id)
        if props is None:
            return
        upsert_contact(
            props,
            hubspot_contact_id=str(hubspot_contact_id),
            address_props=address_props,
        )
    except api.HubSpotRateLimitExhausted:
        handler_method = (
            "ivm.integrations.hubspot.contact_handler.handle_contact_created"
            if action == "create"
            else "ivm.integrations.hubspot.contact_handler.handle_contact_updated"
        )
        frappe.logger("hubspot").warning(
            f"HubSpot: rate limit exhausted on contact {hubspot_contact_id} — re-enqueueing"
        )
        frappe.enqueue(
            handler_method,
            queue="long",
            hubspot_contact_id=hubspot_contact_id,
            hubspot_user_id=hubspot_user_id,
        )
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to {action} Contact for HubSpot contact {hubspot_contact_id}",
            message=frappe.get_traceback(with_context=True),
        )


def upsert_contact(
    properties: dict[str, Any],
    hubspot_contact_id: str | None = None,
    address_props: dict[str, Any] | None = None,
) -> str | None:
    """Create or update a Frappe Contact from a mapped property dict.

    Parameters
    ----------
    properties:
        Dict with keys matching the *values* side of ``CONTACT_FIELD_MAP``
        (``first_name``, ``last_name``, ``email``, ``mobile_no``, ``phone``,
        ``company_name``, ``salutation``, ``designation``, plus custom fields).
    hubspot_contact_id:
        If provided, used to look up / stamp the Contact via
        ``custom_hubspot_contact_id``.  When called from the deal
        association path this may be ``None``, in which case we fall back
        to email-based de-duplication.
    address_props:
        Optional dict with ``address``, ``city``, ``state``, ``country``
        keys used to create/update a linked Address doc.

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
        def _apply_mutations(doc: Any) -> None:
            _update_contact_fields(doc, first_name, last_name, properties)
            _sync_email(doc, email)
            _sync_phone_numbers(doc, properties)
            _set_hubspot_id(doc, hubspot_contact_id)

        _apply_mutations(contact_doc)
        save_doc(contact_doc, "contact", mutate=_apply_mutations)
    else:
        contact_doc = frappe.new_doc("Contact")
        contact_doc.first_name = first_name or email
        contact_doc.last_name = last_name
        contact_doc.company_name = properties.get("company_name") or ""

        _apply_flat_fields(contact_doc, properties)
        _set_hubspot_id(contact_doc, hubspot_contact_id)

        if email:
            contact_doc.append("email_ids", {"email_id": email, "is_primary": 1})

        mobile_raw = (properties.get("mobile_no") or "").strip()
        if mobile_raw:
            mobile_no, mobile_ext = _sanitize_phone(mobile_raw)
            if mobile_no:
                row = {"phone": mobile_no, "is_primary_mobile_no": 1}
                if mobile_ext:
                    row["custom_phone_extension"] = mobile_ext
                contact_doc.append("phone_nos", row)

        phone_raw = (properties.get("phone") or "").strip()
        if phone_raw:
            phone, phone_ext = _sanitize_phone(phone_raw)
            if phone:
                row = {"phone": phone, "is_primary_phone": 1}
                if phone_ext:
                    row["custom_phone_extension"] = phone_ext
                contact_doc.append("phone_nos", row)

        frappe.db.savepoint("before_contact_insert")
        try:
            contact_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.logger("hubspot").info(
                f"Created Contact {contact_doc.name} ({first_name} {last_name})"
            )
        except frappe.DuplicateEntryError:
            frappe.db.rollback(save_point="before_contact_insert")
            frappe.logger("hubspot").warning(
                f"HubSpot: duplicate on insert for '{contact_doc.name}' — falling back to update"
            )
            contact_doc = _find_existing_contact(email, hubspot_contact_id)
            if not contact_doc:
                frappe.logger("hubspot").error(
                    f"HubSpot: could not locate existing Contact after duplicate insert "
                    f"(email={email}, hubspot_id={hubspot_contact_id}) — skipping"
                )
                return None
            def _apply_mutations(doc: Any) -> None:
                _update_contact_fields(doc, first_name, last_name, properties)
                _sync_email(doc, email)
                _sync_phone_numbers(doc, properties)
                _set_hubspot_id(doc, hubspot_contact_id)

            _apply_mutations(contact_doc)
            save_doc(contact_doc, "contact", mutate=_apply_mutations)

    if address_props:
        _sync_contact_address(contact_doc.name, address_props)

    return contact_doc.name


def _fetch_contact_properties(
    hubspot_contact_id: int | str,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Fetch a HubSpot contact and return mapped property + address dicts.

    Returns ``(None, {})`` on failure (already logged).
    """
    try:
        hs_properties = list(CONTACT_FIELD_MAP.keys()) + CONTACT_ADDRESS_PROPERTIES
        contact_data = api.get_contact(
            hubspot_contact_id, properties=hs_properties,
        )
        raw_props = contact_data.get("properties", {})

        mapped = {
            frappe_key: raw_props.get(hs_key) or ""
            for hs_key, frappe_key in CONTACT_FIELD_MAP.items()
        }

        address_props = {
            key: raw_props.get(key) or ""
            for key in CONTACT_ADDRESS_PROPERTIES
        }

        return mapped, address_props
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch contact {hubspot_contact_id}",
            message=frappe.get_traceback(with_context=True),
        )
        return None, {}


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

    _apply_flat_fields(doc, properties)


def _apply_flat_fields(doc: Any, properties: dict[str, Any]) -> None:
    """Apply non-child-table mapped fields to a Contact doc.

    Skips fields that are handled separately (email, phone, mobile_no,
    first_name, last_name, company_name) and validates Link fields.
    """
    meta = frappe.get_meta("Contact")
    for key, value in properties.items():
        if key in _SKIP_FLAT_KEYS or key == "company_name":
            continue
        value = (str(value) if value is not None else "").strip()
        if not value:
            continue

        df = meta.get_field(key)
        if not df:
            continue

        if df.fieldtype == "Link" and df.options:
            if not frappe.db.exists(df.options, value):
                frappe.logger("hubspot").warning(
                    f"{df.options} '{value}' not found — skipping Contact.{key}"
                )
                continue

        doc.set(key, value)


def _sync_email(doc: Any, email: str) -> None:
    """Ensure the primary email is present in the email_ids child table."""
    if not email:
        return

    existing_emails = {row.email_id for row in (doc.get("email_ids") or [])}
    if email not in existing_emails:
        for row in doc.get("email_ids") or []:
            row.is_primary = 0
        doc.append("email_ids", {"email_id": email, "is_primary": 1})


def _sync_phone_numbers(doc: Any, properties: dict[str, Any]) -> None:
    """Ensure mobile and phone numbers are present in the phone_nos child table."""
    existing_phones = {row.phone for row in (doc.get("phone_nos") or [])}

    mobile_raw = (properties.get("mobile_no") or "").strip()
    if mobile_raw:
        mobile_no, mobile_ext = _sanitize_phone(mobile_raw)
        if mobile_no and mobile_no not in existing_phones:
            for row in doc.get("phone_nos") or []:
                row.is_primary_mobile_no = 0
            row = {"phone": mobile_no, "is_primary_mobile_no": 1}
            if mobile_ext:
                row["custom_phone_extension"] = mobile_ext
            doc.append("phone_nos", row)

    phone_raw = (properties.get("phone") or "").strip()
    if phone_raw:
        phone, phone_ext = _sanitize_phone(phone_raw)
        if phone and phone not in existing_phones:
            for row in doc.get("phone_nos") or []:
                row.is_primary_phone = 0
            row = {"phone": phone, "is_primary_phone": 1}
            if phone_ext:
                row["custom_phone_extension"] = phone_ext
            doc.append("phone_nos", row)


def _set_hubspot_id(doc: Any, hubspot_contact_id: str | None) -> None:
    """Stamp the HubSpot contact ID on the doc if the field exists."""
    if not hubspot_contact_id:
        return
    meta = frappe.get_meta("Contact")
    if meta.get_field(HUBSPOT_ID_FIELD):
        doc.set(HUBSPOT_ID_FIELD, hubspot_contact_id)


def _sync_contact_address(
    contact_name: str,
    address_props: dict[str, Any],
) -> None:
    """Create or update an Address doc linked to the Contact."""
    upsert_address(
        address_line1=address_props.get("address", ""),
        city=address_props.get("city", ""),
        state=address_props.get("state", ""),
        country=address_props.get("country", ""),
        link_doctype="Contact",
        link_name=contact_name,
    )
