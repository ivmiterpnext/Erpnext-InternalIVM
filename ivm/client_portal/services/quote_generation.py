"""
Generate Service Quote from CRM Deal and Deployment Locations.
"""

import frappe

from ivm.deployments.services.provision_client_from_deal import get_primary_contact


@frappe.whitelist()
def get_deal_primary_contact(crm_deal):
	"""Return the primary Contact name for a CRM Deal, or None if it has none.

	Used by the Service Quote form's crm_deal change handler to auto-fill the
	contact field, and internally by create_service_quote_from_deal for the
	same resolution.
	"""
	deal = frappe.get_doc("CRM Deal", crm_deal)
	contact = get_primary_contact(deal)
	return contact.name if contact else None


@frappe.whitelist()
def create_service_quote_from_deal(crm_deal):
    """
    Create a Service Quote from a CRM Deal's Deployment Locations.
    
    For each Deployment Location linked to the deal, for each equipment type
    (machines, lockers, vaults, kiosks) with a count > 0, append one Service
    Quote Item row with the equipment label and location name.
    
    Returns {"service_quote": <name>} on success.
    If no Deployment Locations found or none have equipment counts, still
    creates the quote (empty items) but returns a warning message.
    """
    # Load the deal and resolve contact/sales_representative
    deal = frappe.get_doc("CRM Deal", crm_deal)
    
    primary_contact_doc = get_primary_contact(deal)
    if not primary_contact_doc:
        frappe.throw(
            f"CRM Deal {crm_deal} has no primary contact — cannot generate a Service Quote."
        )
    
    if not deal.deal_owner:
        frappe.throw(
            f"CRM Deal {crm_deal} has no deal owner set — cannot determine a sales representative."
        )
    
    # Fetch all Deployment Locations for this deal
    locations = frappe.get_all(
        "Deployment Location",
        filters={"crm_deal": crm_deal},
        fields=[
            "name",
            "location_name",
            "number_of_machines",
            "number_of_primary_lockers",
            "number_of_secondary_lockers",
            "number_of_vaults",
            "number_of_kiosks",
        ],
    )
    
    # Equipment type mappings: (fieldname, label)
    equipment_types = [
        ("number_of_machines", "SmartStation"),
        ("number_of_primary_lockers", "SmartLocker"),
        ("number_of_secondary_lockers", "SmartSync"),
        ("number_of_vaults", "SmartVault"),
        ("number_of_kiosks", "SmartCenter"),
    ]
    
    # Build items from locations
    items = []
    for location in locations:
        for fieldname, label in equipment_types:
            count = location.get(fieldname) or 0
            if count > 0:
                items.append({
                    "deployment_location": location.name,
                    "description": f"{label} — {location.location_name}",
                    "qty": count,
                    "rate": 0,
                })
    
    # Create Service Quote with explicitly resolved contact and sales_representative
    quote_doc = frappe.get_doc({
        "doctype": "Service Quote",
        "crm_deal": crm_deal,
        "contact": primary_contact_doc.name,
        "sales_representative": deal.deal_owner,
        "items": items,
    })
    quote_doc.insert(ignore_permissions=True)
    
    # Return response
    if not locations or not items:
        return {
            "service_quote": quote_doc.name,
            "warning": "No Deployment Locations found or none have equipment counts. Quote created as draft.",
        }
    
    return {"service_quote": quote_doc.name}
