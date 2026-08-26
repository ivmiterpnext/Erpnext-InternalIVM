"""
Provision a Customer and iCorp client/contact when a CRM Deal is won.

New Business flow
-----------------
1. Create a Frappe **Customer** from the deal's CRM Organization (or reuse an
   existing one if a match is found).
2. Create an **iCorp Contact** from the deal's primary Frappe Contact.
3. Create an **iCorp Client** referencing the new iCorp contact.
4. Store the iCorp client ID on the Customer and link the Customer back to
   the CRM Deal so downstream project provisioning inherits the link.

Existing Business flow
----------------------
1. Check ``custom_customer`` already set on the deal — either synced from
   HubSpot's ``client_id`` property or manually selected in Frappe.
2. If not set, fall back to matching by CRM Organization name (only available
   for deals where the org was synced from HubSpot).
3. If neither resolves a Customer, raise an error — the deal cannot be won
   without a linked Customer.
4. Write the resolved Customer back to ``custom_customer`` on the deal so
   downstream project provisioning inherits the link.

If any iCorp API call fails the Customer is still created/linked — an error is
logged for manual follow-up and the deal is not blocked from moving to Won.
"""

from __future__ import annotations

from typing import Any

import frappe

from ivm.integrations.icorp import extract_id, icorp_api_post

_LOG = "ivm.deployments.provision_client"

_ORG_TO_CUSTOMER_FIELDS: dict[str, str] = {
    "industry": "industry",
    "website": "website",
    "annual_revenue": "annual_revenue",
    "no_of_employees": "employees",
}


def _get_primary_value(
    rows: list[Any], value_field: str, primary_field: str = "is_primary",
) -> str:
    """Return the primary row's value, falling back to the first row."""
    for row in rows:
        if row.get(primary_field):
            return row.get(value_field) or ""
    return rows[0].get(value_field) or "" if rows else ""


def provision_customer_and_icorp_client(crm_deal_name: str) -> str | None:
    """Provision a Customer and iCorp client for a New Business deal.

    Returns the Customer name, or ``None`` if provisioning failed before the
    Customer could be created.
    """
    log = frappe.logger(_LOG)
    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    if not deal.organization:
        frappe.log_error(
            title=f"Client provisioning skipped for {crm_deal_name}",
            message="CRM Deal has no linked CRM Organization.",
        )
        return None

    org = frappe.get_doc("CRM Organization", deal.organization)

    customer_name = _find_existing_customer(org)
    if not customer_name:
        customer_name = _create_customer_from_org(org, deal.custom_pipeline)

    if not customer_name:
        return None

    primary_contact_doc = get_primary_contact(deal)

    if primary_contact_doc:
        _link_contact_to_customer(primary_contact_doc, customer_name)

    icorp_client_id: int | None = None

    if primary_contact_doc:
        icorp_contact_id = _create_icorp_contact(primary_contact_doc)
        if icorp_contact_id is not None:
            icorp_client_id = _create_icorp_client(
                org.organization_name, icorp_contact_id,
            )
    else:
        frappe.log_error(
            title=f"iCorp provisioning: no primary contact on {crm_deal_name}",
            message=(
                "No primary contact found on the CRM Deal. "
                "Customer was created but iCorp client/contact were not. "
                "Please create them manually."
            ),
        )

    if icorp_client_id is not None:
        frappe.db.set_value("Customer", customer_name, "icorp_client_id", str(icorp_client_id))
        log.info(f"Linked Customer '{customer_name}' to iCorp client {icorp_client_id}")

    frappe.db.set_value("CRM Deal", crm_deal_name, "custom_customer", customer_name)

    return customer_name


def link_existing_customer_to_deal(crm_deal_name: str) -> str:
    """Resolve and link an existing Customer to an Existing Business deal.

    Resolution order:
    1. ``custom_customer`` already set on the deal (synced from HubSpot or
       manually selected in Frappe).
    2. Match a Customer by the deal's CRM Organization name, if an org is
       linked (only reliable for deals where the org was synced from HubSpot).

    Returns the Customer name.
    Raises ``frappe.ValidationError`` if no Customer can be resolved.
    """
    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    # 1. Check custom_customer already on the deal.  The HubSpot sync
    #    resolves the iCorp numeric client ID → Customer name at sync time
    #    (see _apply_client_id in deal_handler.py), so this field should
    #    already hold a valid Customer name for deals coming from HubSpot.
    #    It may also be set manually in Frappe.
    customer_name: str | None = None
    if deal.custom_customer and frappe.db.exists("Customer", deal.custom_customer):
        customer_name = deal.custom_customer
        frappe.logger(_LOG).info(
            f"Resolved existing Customer '{customer_name}' from "
            f"custom_customer on deal {crm_deal_name}"
        )

    # 2. Fall back to matching by CRM Organization name if an org is linked.
    #    Not available for older deals where the org was never synced from HubSpot.
    if not customer_name and deal.organization:
        org = frappe.get_doc("CRM Organization", deal.organization)
        customer_name = _find_existing_customer(org)
        if customer_name:
            frappe.logger(_LOG).info(
                f"Resolved existing Customer '{customer_name}' from org name "
                f"'{org.organization_name}' for deal {crm_deal_name}"
            )

    if not customer_name:
        frappe.throw(
            "Cannot mark this deal as Won — no matching Customer was found. "
            "Please set the 'Client' field on the deal to the correct Customer "
            "before winning an Existing Business deal.",
            title="Customer Not Found",
        )

    # Write back so project provisioning picks it up.
    frappe.db.set_value("CRM Deal", crm_deal_name, "custom_customer", customer_name)
    return customer_name


def _find_existing_customer(org: Any) -> str | None:
    """Return the name of an existing Customer that matches the CRM Organization.

    Matches on ``customer_name`` plus key fields (industry, website).  Returns
    ``None`` if no match is found.
    """
    existing = frappe.db.get_value(
        "Customer",
        {"customer_name": org.organization_name},
        ["name", "industry", "website"],
        as_dict=True,
    )
    if not existing:
        return None

    org_industry = (org.industry or "").strip()
    org_website = (org.website or "").strip()
    cust_industry = (existing.get("industry") or "").strip()
    cust_website = (existing.get("website") or "").strip()

    if org_industry and cust_industry and org_industry != cust_industry:
        return None
    if org_website and cust_website and org_website != cust_website:
        return None

    return existing["name"]


def _customer_group_from_pipeline(pipeline: str | None) -> str:
    """Map a CRM Pipeline to a Customer Group."""
    if pipeline == "Government Sales":
        return "Government"
    return "Commercial"


def _create_customer_from_org(org: Any, pipeline: str | None = None) -> str | None:
    """Create a new Frappe Customer from a CRM Organization."""
    try:
        customer = frappe.new_doc("Customer")
        customer.customer_name = org.organization_name
        customer.customer_type = "Company"
        customer.customer_group = _customer_group_from_pipeline(pipeline)

        for org_field, cust_field in _ORG_TO_CUSTOMER_FIELDS.items():
            value = org.get(org_field)
            if value is not None and value != "":
                customer.set(cust_field, value)

        customer.insert(ignore_permissions=True)

        frappe.logger(_LOG).info(
            f"Created Customer '{customer.name}' from CRM Organization '{org.organization_name}'"
        )
        return customer.name

    except Exception:
        frappe.log_error(
            title=f"Failed to create Customer from CRM Organization '{org.organization_name}'",
            message=frappe.get_traceback(with_context=True),
        )
        return None


def _link_contact_to_customer(contact_doc: Any, customer_name: str) -> None:
    """Link a Frappe Contact to a Customer via the Contact's links child table."""
    for link in (contact_doc.get("links") or []):
        if link.link_doctype == "Customer" and link.link_name == customer_name:
            return

    contact_doc.append("links", {
        "link_doctype": "Customer",
        "link_name": customer_name,
    })
    contact_doc.save(ignore_permissions=True)

    frappe.logger(_LOG).info(
        f"Linked Contact '{contact_doc.name}' to Customer '{customer_name}'"
    )


def get_primary_contact(deal: Any) -> Any | None:
    """Return the Frappe Contact doc for the deal's primary contact."""
    contacts = deal.get("contacts") or []

    primary_row = next((r for r in contacts if r.is_primary), None)
    if not primary_row and contacts:
        primary_row = contacts[0]

    if not primary_row:
        return None

    return frappe.get_doc("Contact", primary_row.contact)


def _create_icorp_contact(contact_doc: Any) -> int | None:
    """Create a contact in iCorp from a Frappe Contact.

    Returns the iCorp contact ID, or ``None`` on failure.
    """
    email = _get_primary_value(
        contact_doc.get("email_ids") or [], "email_id",
    )
    phone = _get_primary_value(
        contact_doc.get("phone_nos") or [], "phone", "is_primary_phone",
    )

    payload = {
        "first_name": contact_doc.first_name or "",
        "middle_name": contact_doc.middle_name or "",
        "last_name": contact_doc.last_name or "",
        "email_address": email,
        "phone1": phone,
        "phone_type_id1": 1,
        "title": contact_doc.designation or "",
    }

    try:
        response = icorp_api_post("Contact", payload)

        if isinstance(response, dict) and response.get("error"):
            frappe.log_error(
                title="iCorp: failed to create contact",
                message=str(response),
            )
            return None

        return extract_id(response, "contact")

    except Exception:
        frappe.log_error(
            title="iCorp: failed to create contact",
            message=frappe.get_traceback(with_context=True),
        )
        return None


def _create_icorp_client(client_name: str, icorp_contact_id: int) -> int | None:
    """Create a client in iCorp.

    Returns the iCorp client ID, or ``None`` on failure.
    """
    payload = {
        "name": client_name,
        "is_active": True,
        "is_enhanced_client": False,
        "using_enhanced_assignments": False,
        "restriction_priority_type_id": 2,
        "primary_contact_id": icorp_contact_id,
        "check_frequency_type_code": "M",
        "fee_rate_id": 1,
    }

    try:
        response = icorp_api_post("Client", payload)

        if isinstance(response, dict) and response.get("error"):
            frappe.log_error(
                title=f"iCorp: failed to create client '{client_name}'",
                message=str(response),
            )
            return None

        return extract_id(response, "client")

    except Exception:
        frappe.log_error(
            title=f"iCorp: failed to create client '{client_name}'",
            message=frappe.get_traceback(with_context=True),
        )
        return None
