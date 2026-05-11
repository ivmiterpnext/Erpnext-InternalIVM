from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client


def fetch_first_deployment_site(hubspot_deal_id: int | str) -> dict[str, Any] | None:
    """Fetch the first deployment site's properties for a HubSpot deal.

    Returns the site properties dict, or None if no deployment sites found.
    """
    hubspot_deal_id_str = str(hubspot_deal_id)

    try:
        associations = hubspot_client.get_deal_associations(hubspot_deal_id_str)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch deployment site associations for deal {hubspot_deal_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return None

    if not associations:
        frappe.logger("hubspot").info(
            f"No deployment sites associated with HubSpot deal {hubspot_deal_id_str}"
        )
        return None

    # Fetch the first deployment site
    site_id = associations[0]
    try:
        site_data = hubspot_client.get_custom_object("2-226377266", site_id)
        return site_data.get("properties", {})
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch deployment site {site_id} for deal {hubspot_deal_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return None


def process_deployment_sites(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Fetch deployment sites and populate the CRM Deal with the site data.

    For each deployment site associated with the deal, fetch the site properties
    and store them on the CRM Deal. Project creation is handled by the CRM Deal
    on_update hook.
    """
    hubspot_deal_id_str = str(hubspot_deal_id)

    try:
        associations = hubspot_client.get_deal_associations(hubspot_deal_id_str)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch deployment site associations for deal {hubspot_deal_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not associations:
        frappe.logger("hubspot").info(
            f"No deployment sites associated with HubSpot deal {hubspot_deal_id_str}"
        )
        return

    for association in associations:
        try:
            site_data = hubspot_client.get_custom_object("2-226377266", association)
            site_properties: dict[str, Any] = site_data.get("properties", {})

            _add_deal_comment(
                crm_deal_name=crm_deal_name,
                site_id=str(association),
                site_name=site_properties.get("site_location_name", str(association)),
                site_properties=site_properties,
            )
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to process deployment site {association} for deal {hubspot_deal_id_str}",
                message=frappe.get_traceback(with_context=True),
            )


def _add_deal_comment(
    crm_deal_name: str,
    site_id: str,
    site_name: str,
    site_properties: dict[str, Any],
) -> None:
    """Add a Comment on the CRM Deal documenting the deployment site."""
    props_summary = "\n".join(f"- **{k}**: {v}" for k, v in site_properties.items() if v)

    comment_text = (
        f"**Deployment Site** (HubSpot ID: {site_id})\n"
        f"**Name**: {site_name}\n"
        f"{props_summary}"
    )

    frappe.get_doc(
        {
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": "CRM Deal",
            "reference_name": crm_deal_name,
            "content": comment_text,
        }
    ).insert(ignore_permissions=True)
