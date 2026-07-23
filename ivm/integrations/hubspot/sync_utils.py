"""Generic sync utilities for HubSpot to Frappe document synchronization."""

from typing import Any, Callable

import frappe
from frappe.utils import flt

from ivm.integrations.hubspot.constants import HUBSPOT_USER

ValueTransform = Callable[[Any, Any], None]
"""A value transform receives ``(doc, raw_value)`` and mutates the doc directly."""

_LOG = "hubspot"
_TRUTHY = frozenset({"true", "1", "yes"})
_FALSY = frozenset({"false", "0", "no"})
_BOOLEAN_ISH = _TRUTHY | _FALSY


def coerce_value(value: Any, df: Any = None) -> Any:
    """Coerce a single HubSpot value based on the target Frappe field type."""
    if df is None:
        if isinstance(value, str) and value.lower() in _BOOLEAN_ISH:
            return 1 if value.lower() in _TRUTHY else 0
        return value

    str_lower = str(value).lower().strip()
    is_boolean_ish = str_lower in _BOOLEAN_ISH

    if df.fieldtype == "Check":
        if is_boolean_ish:
            return 1 if str_lower in _TRUTHY else 0
        return value

    if df.fieldtype == "Select":
        options = [o for o in (df.options or "").split("\n") if o]

        if is_boolean_ish and "Yes" in options and "No" in options:
            return "Yes" if str_lower in _TRUTHY else "No"

        if str(value) in options:
            return str(value)

        if is_boolean_ish:
            return ""

        frappe.logger(_LOG).warning(
            f"HubSpot value '{value}' is not a valid option for "
            f"Select field '{df.fieldname}' (options: {options}) — clearing"
        )
        return ""

    return value


def apply_field_map(
    doc: Any,
    properties: dict[str, Any],
    field_map: dict[str, str],
    value_transforms: dict[str, ValueTransform] | None = None,
) -> None:
    """Map HubSpot properties onto a Frappe doc using *field_map*.

    Custom transforms take precedence. The generic path skips empty values,
    validates Link fields, and truncates ISO timestamps for Date fields.
    """
    transforms = value_transforms or {}
    meta = frappe.get_meta(doc.doctype)

    for hs_key, frappe_field in field_map.items():
        value = properties.get(hs_key)

        if frappe_field in transforms:
            transforms[frappe_field](doc, value)
            continue

        if value is None or value == "":
            continue

        df = meta.get_field(frappe_field)

        if df and df.fieldtype == "Link" and df.options:
            if not frappe.db.exists(df.options, value):
                frappe.logger(_LOG).warning(
                    f"{df.options} '{value}' (from {hs_key}) not found — skipping {frappe_field}"
                )
                continue

        if df and df.fieldtype == "Date" and isinstance(value, str) and "T" in value:
            value = value.split("T")[0]

        doc.set(frappe_field, value)


def save_doc(
    doc: Any,
    label: str = "hubspot",
    mutate: Callable[[Any], None] | None = None,
    max_retries: int = 3,
) -> None:
    """Save a Frappe doc with ignore_permissions, skip link validation, and log the result.

    On ``TimestampMismatchError`` (concurrent modification), reloads the
    doc and retries up to *max_retries* times. If *mutate* is provided,
    it is called with the freshly-reloaded doc after each reload to
    re-apply any field changes that were made before the failed save
    (since ``reload()`` discards in-memory mutations).
    """
    doc.flags.ignore_links = True
    attempt = 0
    while True:
        try:
            doc.save(ignore_permissions=True)
            break
        except frappe.exceptions.TimestampMismatchError:
            attempt += 1
            if attempt > max_retries:
                raise
            frappe.logger(_LOG).warning(
                f"{doc.doctype} {doc.name} modified concurrently — "
                f"reloading and retrying save (attempt {attempt}/{max_retries})"
            )
            doc.reload()
            if mutate:
                mutate(doc)

    frappe.logger(_LOG).info(
        f"Synced {label} fields on {doc.doctype} {doc.name}"
    )


def lookup_or_create(
    doctype: str,
    hubspot_id_field: str,
    hubspot_id: str,
    defaults: dict[str, Any] | None = None,
) -> tuple[Any, bool]:
    """Return ``(doc, is_new)`` for the given HubSpot ID, creating the doc if it doesn't exist."""
    hubspot_id = str(hubspot_id)

    existing_name = frappe.db.get_value(
        doctype, {hubspot_id_field: hubspot_id}, "name",
    )

    if existing_name:
        return frappe.get_doc(doctype, existing_name), False

    doc = frappe.new_doc(doctype)
    doc.set(hubspot_id_field, hubspot_id)
    for key, val in (defaults or {}).items():
        doc.set(key, val)

    frappe.db.savepoint("before_lookup_or_create_insert")
    try:
        doc.insert(ignore_permissions=True)
        frappe.logger(_LOG).info(
            f"Created {doctype} {doc.name} (HubSpot ID {hubspot_id})"
        )
        return doc, True
    except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
        frappe.db.rollback(save_point="before_lookup_or_create_insert")
        frappe.logger(_LOG).warning(
            f"HubSpot: duplicate on insert for {doctype} '{doc.name}' — concurrent write, fetching existing"
        )
        existing_name = frappe.db.get_value(
            doctype, {hubspot_id_field: hubspot_id}, "name",
        )
        if existing_name:
            return frappe.get_doc(doctype, existing_name), False
        raise


def upsert_address(
    address_line1: str,
    city: str = "",
    state: str = "",
    country: str = "",
    pincode: str = "",
    link_doctype: str = "",
    link_name: str = "",
) -> str | None:
    """Create or update an Address linked to *link_doctype* / *link_name*.

    Returns the Address ``name``, or ``None`` if *address_line1* is empty.
    """
    address_line1 = (address_line1 or "").strip()
    if not address_line1:
        return None

    city, state, country, pincode = (
        (v or "").strip() for v in (city, state, country, pincode)
    )

    if country and not frappe.db.exists("Country", country):
        frappe.logger(_LOG).warning(
            f"Country '{country}' not found — skipping address for {link_doctype} {link_name}"
        )
        return None

    existing_address = _find_linked_address(link_doctype, link_name)

    if existing_address:
        doc = frappe.get_doc("Address", existing_address)
        doc.address_line1 = address_line1
        for field, value in {"city": city, "state": state, "country": country, "pincode": pincode}.items():
            if value:
                doc.set(field, value)
        doc.save(ignore_permissions=True)
        frappe.logger(_LOG).info(f"Updated Address {doc.name} for {link_doctype} {link_name}")
        return doc.name

    doc = frappe.get_doc({
        "doctype": "Address",
        "address_title": link_name,
        "address_type": "Office",
        "address_line1": address_line1,
        "city": city or "Unknown",
        "state": state,
        "country": country or "United States",
        "pincode": pincode,
        "links": [
            {"link_doctype": link_doctype, "link_name": link_name},
        ],
    })
    doc.insert(ignore_permissions=True)
    frappe.logger(_LOG).info(f"Created Address {doc.name} for {link_doctype} {link_name}")

    parent_meta = frappe.get_meta(link_doctype)
    if parent_meta.get_field("address"):
        frappe.db.set_value(link_doctype, link_name, "address", doc.name)

    return doc.name


def _find_linked_address(link_doctype: str, link_name: str) -> str | None:
    """Find an existing Address linked to the given document via Dynamic Link."""
    if not link_doctype or not link_name:
        return None
    result = frappe.db.get_value(
        "Dynamic Link",
        {"link_doctype": link_doctype, "link_name": link_name, "parenttype": "Address"},
        "parent",
    )
    return result


def bucket_employee_count(count_str: str | None) -> str:
    """Convert a raw employee count to a Frappe select range."""
    if not count_str:
        return ""
    try:
        count = int(flt(count_str))
    except (ValueError, TypeError):
        return ""
    if count <= 0:
        return ""
    if count <= 10:
        return "1-10"
    if count <= 50:
        return "11-50"
    if count <= 200:
        return "51-200"
    if count <= 500:
        return "201-500"
    if count <= 1000:
        return "501-1000"
    return "1000+"


def set_acting_user(hubspot_user_id: int | str | None = None) -> None:
    """Set the Frappe session user to the HubSpot integration service account.

    All HubSpot sync operations run as the dedicated ``HUBSPOT_USER`` service
    account so they have consistent, sufficient permissions regardless of
    which HubSpot user triggered the webhook. ``hubspot_user_id`` is accepted
    for backwards compatibility but is no longer used to switch the acting
    user — attribution (e.g. ``doc.owner``, ``doc.assigned_to``) should be
    set explicitly by callers instead of relying on the session user.
    """
    frappe.set_user(HUBSPOT_USER)
