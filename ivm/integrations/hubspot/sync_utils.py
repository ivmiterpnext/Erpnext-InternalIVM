"""Generic sync utilities for HubSpot to Frappe document synchronization."""

from typing import Any, Callable

import frappe
from frappe.utils import flt

from ivm.integrations.hubspot.constants import HUBSPOT_USER

# A value transform receives (doc, raw_value) and mutates the doc directly.
ValueTransform = Callable[[Any, Any], None]

# Values HubSpot uses for booleans (case-insensitive).
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

        frappe.logger("hubspot").warning(
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

        # --- Custom transform takes precedence ---
        if frappe_field in transforms:
            transforms[frappe_field](doc, value)
            continue

        # --- Generic path ---
        if value is None or value == "":
            continue

        df = meta.get_field(frappe_field)

        # Validate Link fields
        if df and df.fieldtype == "Link" and df.options:
            if not frappe.db.exists(df.options, value):
                frappe.logger("hubspot").warning(
                    f"{df.options} '{value}' (from {hs_key}) not found — skipping {frappe_field}"
                )
                continue

        # Truncate ISO datetime strings for Date fields
        if df and df.fieldtype == "Date" and isinstance(value, str) and "T" in value:
            value = value.split("T")[0]

        doc.set(frappe_field, value)


def save_doc(doc: Any, logger_prefix: str = "hubspot") -> None:
    """Save a Frappe doc with ignore_permissions and log the result."""
    doc.save(ignore_permissions=True)
    frappe.logger("hubspot").info(
        f"Synced {logger_prefix} fields on {doc.doctype} {doc.name}"
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
    doc.insert(ignore_permissions=True)

    frappe.logger("hubspot").info(
        f"Created {doctype} {doc.name} (HubSpot ID {hubspot_id})"
    )
    return doc, True


def set_hubspot_user() -> None:
    """Set the current Frappe user to the HubSpot service account."""
    frappe.set_user(HUBSPOT_USER)


def upsert_address(
    address_line1: str,
    city: str = "",
    state: str = "",
    country: str = "",
    pincode: str = "",
    link_doctype: str = "",
    link_name: str = "",
) -> str | None:
    """Create or update an Address doc linked to a Frappe document.

    Parameters
    ----------
    address_line1:
        The street address.  If empty, the Address doc is **skipped entirely**.
    city, state, country, pincode:
        Additional address fields.
    link_doctype:
        The DocType to link the address to (e.g. ``"Contact"``, ``"CRM Organization"``).
    link_name:
        The ``name`` of the document to link the address to.

    Returns
    -------
    str | None
        The Address ``name``, or ``None`` if skipped.
    """
    address_line1 = (address_line1 or "").strip()
    if not address_line1:
        return None

    city = (city or "").strip()
    state = (state or "").strip()
    country = (country or "").strip()
    pincode = (pincode or "").strip()

    # Validate country against Frappe's Country doctype
    if country and not frappe.db.exists("Country", country):
        frappe.logger("hubspot").warning(
            f"Country '{country}' not found in Country doctype — skipping address "
            f"for {link_doctype} {link_name}"
        )
        return None

    # Check for an existing Address linked to this document
    existing_address = _find_linked_address(link_doctype, link_name)

    if existing_address:
        doc = frappe.get_doc("Address", existing_address)
        doc.address_line1 = address_line1
        if city:
            doc.city = city
        if state:
            doc.state = state
        if country:
            doc.country = country
        if pincode:
            doc.pincode = pincode
        doc.save(ignore_permissions=True)
        frappe.logger("hubspot").info(
            f"Updated Address {doc.name} for {link_doctype} {link_name}"
        )
        return doc.name

    # Create a new Address doc
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
    frappe.logger("hubspot").info(
        f"Created Address {doc.name} for {link_doctype} {link_name}"
    )

    # Link the address back to the parent document if it has an address field
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
    """Convert a raw employee count (e.g. ``"150"``) to a Frappe select range.

    Returns one of: ``"1-10"``, ``"11-50"``, ``"51-200"``, ``"201-500"``,
    ``"501-1000"``, ``"1000+"``, or ``""`` if the value cannot be parsed.
    """
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
    """Set the Frappe session user based on the HubSpot user who triggered the event.

    Resolves the HubSpot user/owner ID to an email via the Owners API,
    then checks if that email corresponds to a Frappe User.  Falls back
    to the HubSpot service account when resolution fails or no matching
    Frappe user exists.

    Owner email resolution is cached in ``hubspot_client.get_owner_email``
    so repeated calls for the same owner ID within a single worker process
    don't hit the HubSpot API again.
    """
    if not hubspot_user_id:
        frappe.set_user(HUBSPOT_USER)
        return

    from ivm.integrations.hubspot import hubspot_client

    email = hubspot_client.get_owner_email(hubspot_user_id)

    if email and frappe.db.exists("User", email):
        frappe.set_user(email)
    else:
        frappe.set_user(HUBSPOT_USER)
