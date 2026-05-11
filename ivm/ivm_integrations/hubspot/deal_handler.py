from datetime import timedelta
from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client

# Weeks to add to the deal close date to calculate the target ship date.
_TARGET_SHIP_WEEKS = 5


def handle_deal_created(hubspot_deal_id: int | str) -> None:
    """Create a CRM Deal from a newly created HubSpot deal.

    Populates the deal's deployment fields from HubSpot data.
    Called asynchronously via frappe.enqueue from the webhook handler.
    """
    try:
        _create_crm_deal(hubspot_deal_id)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to create CRM Deal for deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )


def handle_deal_closed_won(hubspot_deal_id: int | str) -> None:
    """Handle a HubSpot deal moving to the won stage.

    Updates the existing CRM Deal status to Won. The CRM Deal on_update hook
    in ivm.deployments.hooks.deal will handle Project creation.

    Called asynchronously via frappe.enqueue from the webhook handler.
    """
    try:
        crm_deal_name = _update_crm_deal_to_won(hubspot_deal_id)
        if crm_deal_name:
            _populate_deployment_fields(hubspot_deal_id, crm_deal_name)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to handle closedwon for deal {hubspot_deal_id}",
            message=frappe.get_traceback(with_context=True),
        )


def _create_crm_deal(hubspot_deal_id: int | str) -> str | None:
    """Fetch deal data from HubSpot and create a CRM Deal document.

    Returns the name of the created CRM Deal, or None if it already exists.
    """
    hubspot_deal_id_str = str(hubspot_deal_id)

    # Idempotency check
    if frappe.db.exists("CRM Deal", {"custom_hubspot_deal": hubspot_deal_id_str}):
        frappe.log_error(
            title=f"HubSpot: CRM Deal already exists for deal {hubspot_deal_id_str}",
            message="Skipping duplicate deal creation.",
        )
        return None

    hubspot_data = hubspot_client.get_deal(hubspot_deal_id)
    properties: dict[str, Any] = hubspot_data.get("properties", {})

    deal = frappe.new_doc("CRM Deal")
    deal.update(
        {
            "custom_hubspot_deal": hubspot_deal_id_str,
            "deal_value": _parse_amount(properties.get("amount")),
            "status": "Qualification",
            "custom_hubspot_id": properties.get("dealname"),
        }
    )
    deal.insert(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger("hubspot").info(f"Created CRM Deal {deal.name} for HubSpot deal {hubspot_deal_id_str}")
    return deal.name


def _update_crm_deal_to_won(hubspot_deal_id: int | str) -> str | None:
    """Find the CRM Deal by HubSpot ID and update its status to Won.

    Returns the CRM Deal name, or None if not found.
    """
    hubspot_deal_id_str = str(hubspot_deal_id)

    crm_deal_name = frappe.db.get_value(
        "CRM Deal",
        {"custom_hubspot_deal": hubspot_deal_id_str},
        "name",
    )

    if not crm_deal_name:
        frappe.log_error(
            title=f"HubSpot: CRM Deal not found for deal {hubspot_deal_id_str}",
            message="Cannot update status to Won — no matching CRM Deal found.",
        )
        return None

    frappe.db.set_value("CRM Deal", crm_deal_name, "status", "Won")
    frappe.db.commit()

    frappe.logger("hubspot").info(
        f"Updated CRM Deal {crm_deal_name} to Won for HubSpot deal {hubspot_deal_id_str}"
    )
    return crm_deal_name


def _populate_deployment_fields(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Fetch deployment site data from HubSpot and populate CRM Deal fields.

    Writes flat fields and child table rows (machine details) onto the CRM Deal
    so that the on_update hook can create the Project from them.
    """
    from ivm.ivm_integrations.hubspot.deployment_site_handler import (
        fetch_first_deployment_site,
    )

    site_properties = fetch_first_deployment_site(hubspot_deal_id)
    if not site_properties:
        return

    # Map HubSpot site properties to CRM Deal custom fields
    SITE_TO_DEAL_FIELDS: dict[str, str] = {
        "site_location_name": "custom_location_name",
        "equipment_type": "custom_equipment_type",
        "machine_ownership_status": "custom_machine_ownership_status",
        "wrap_type": "custom_wrap_type",
        "card_reader_type": "custom_card_reader_type",
        "connectivity_type": "custom_connectivity_type",
        "locale": "custom_locale",
        "expedited_delivery": "custom_expedited_delivery",
        "install_type": "custom_install_type",
        "sales_rep": "custom_sales_rep",
        "ior": "custom_ior",
        "opportunity_term": "custom_opportunity_term",
        "custom_shipping_address": "custom_shipping_address",
        "billing_address": "custom_billing_address",
        "po_and_tracking": "custom_po_and_tracking",
    }

    # Customer Link fields — resolved separately because they need a DB lookup
    CUSTOMER_LINK_FIELDS: dict[str, str] = {
        "client_id": "custom_client_id",
        "master_client_id": "custom_master_client_id",
    }

    # Map HubSpot nested machine lists to CRM Deal child table fields
    SITE_TO_DEAL_CHILD_TABLES: dict[str, str] = {
        "smartstations": "custom_deal_smartstation_details",
        "smartlockers": "custom_deal_smartlocker_details",
        "smartsyncs": "custom_deal_smartsync_details",
        "smartvaults": "custom_deal_smartvault_details",
        "smartcenters": "custom_deal_smartcenter_details",
    }

    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    # Populate flat fields
    for site_key, deal_field in SITE_TO_DEAL_FIELDS.items():
        value = site_properties.get(site_key)
        if value is not None and value != "":
            deal.set(deal_field, value)

    # Resolve Customer Link fields (HubSpot sends a customer name string;
    # we look up the matching Customer record by name).
    for site_key, deal_field in CUSTOMER_LINK_FIELDS.items():
        value = site_properties.get(site_key)
        if value and frappe.db.exists("Customer", value):
            deal.set(deal_field, value)
        elif value:
            frappe.logger("hubspot").warning(
                f"Customer '{value}' (from {site_key}) not found — skipping {deal_field}"
            )

    # Calculate target ship date (N weeks after deal close)
    close_date = deal.get("closed_date") or frappe.utils.today()
    deal.set(
        "custom_target_ship_date",
        frappe.utils.add_to_date(close_date, weeks=_TARGET_SHIP_WEEKS),
    )

    # Populate child table rows from nested machine objects
    for source_key, table_field in SITE_TO_DEAL_CHILD_TABLES.items():
        machines = site_properties.get(source_key)
        if not machines:
            continue
        if isinstance(machines, dict):
            machines = [machines]
        if not isinstance(machines, list):
            continue

        for machine in machines:
            if not isinstance(machine, dict):
                continue
            row = {k: v for k, v in machine.items() if v is not None and v != ""}
            if row:
                deal.append(table_field, row)

    deal.save(ignore_permissions=True)
    frappe.db.commit()

    # Create / link contacts from the deployment site data
    _ensure_contacts(crm_deal_name, site_properties.get("contacts") or [])

    frappe.logger("hubspot").info(
        f"Populated deployment fields on CRM Deal {crm_deal_name} from HubSpot"
    )


def _ensure_contacts(
    crm_deal_name: str,
    contacts: list[dict[str, Any]],
) -> None:
    """Create Contact records (if needed) and link them to the CRM Deal.

    Each entry in *contacts* should be a dict with any of:
        first_name, last_name, email, mobile_no, phone, company_name

    De-duplicates on email: if a Contact with the same primary email already
    exists, it is reused rather than created again.  The first contact in the
    list is marked ``is_primary`` on the deal.

    Example call from a HubSpot handler::

        _ensure_contacts(deal_name, [
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane@example.com",
                "mobile_no": "555-0100",
            },
        ])
    """
    if not contacts:
        return

    deal = frappe.get_doc("CRM Deal", crm_deal_name)

    for idx, entry in enumerate(contacts):
        email = (entry.get("email") or "").strip()
        first_name = (entry.get("first_name") or "").strip()
        last_name = (entry.get("last_name") or "").strip()

        if not first_name and not email:
            continue

        # Try to find an existing Contact by email first
        contact_name = None
        if email:
            contact_name = frappe.db.get_value(
                "Contact",
                {"email_id": email},
                "name",
            )

        if not contact_name:
            # Create a new Contact
            contact_doc = frappe.new_doc("Contact")
            contact_doc.first_name = first_name or email
            contact_doc.last_name = last_name
            contact_doc.company_name = entry.get("company_name") or ""

            if email:
                contact_doc.append(
                    "email_ids",
                    {"email_id": email, "is_primary": 1},
                )

            mobile_no = (entry.get("mobile_no") or "").strip()
            if mobile_no:
                contact_doc.append(
                    "phone_nos",
                    {"phone": mobile_no, "is_primary_mobile_no": 1},
                )

            phone = (entry.get("phone") or "").strip()
            if phone:
                contact_doc.append(
                    "phone_nos",
                    {"phone": phone, "is_primary_phone": 1},
                )

            contact_doc.insert(ignore_permissions=True)
            contact_name = contact_doc.name

            frappe.logger("hubspot").info(
                f"Created Contact {contact_name} ({first_name} {last_name})"
            )

        # Skip if this contact is already linked to the deal
        already_linked = any(
            row.contact == contact_name for row in (deal.get("contacts") or [])
        )
        if already_linked:
            continue

        deal.append(
            "contacts",
            {"contact": contact_name, "is_primary": 1 if idx == 0 else 0},
        )

    deal.save(ignore_permissions=True)
    frappe.db.commit()


def _parse_amount(value: Any) -> float:
    """Safely parse a deal amount to a float, defaulting to 0."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
