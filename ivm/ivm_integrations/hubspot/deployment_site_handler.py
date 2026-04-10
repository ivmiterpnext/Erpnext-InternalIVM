from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client


def process_deployment_sites(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
	"""Fetch deployment sites associated with a HubSpot deal and create Projects.

	For each deployment site associated with the deal:
	  1. Fetch the deployment site custom object from HubSpot
	  2. Store a reference on the CRM Deal as a comment
	  3. Create an ERPNext Project
	"""
	hubspot_deal_id_str = str(hubspot_deal_id)

	# Fetch associated deployment site IDs
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
			_process_single_deployment_site(
				site_id=association,
				hubspot_deal_id_str=hubspot_deal_id_str,
				crm_deal_name=crm_deal_name,
			)
		except Exception:
			frappe.log_error(
				title=f"HubSpot: failed to process deployment site {association} for deal {hubspot_deal_id_str}",
				message=frappe.get_traceback(with_context=True),
			)


def _process_single_deployment_site(
	site_id: int | str,
	hubspot_deal_id_str: str,
	crm_deal_name: str,
) -> None:
	"""Fetch a single deployment site from HubSpot and create a Project for it."""
	site_id_str = str(site_id)

	# Idempotency: skip if a Project already exists for this deployment site + deal
	# if frappe.db.exists(
	# 	"Project",
	# 	{
	# 		"custom_hubspot_deal": hubspot_deal_id_str,
	# 		"custom_hubspot_deployment_site_id": site_id_str,
	# 	},
	# ):
	# 	frappe.logger("hubspot").info(
	# 		f"Project already exists for deployment site {site_id_str} / deal {hubspot_deal_id_str}"
	# 	)
	# 	return
	#
	# Fetch deployment site details from HubSpot
	site_data = hubspot_client.get_custom_object(
		"2-226377266",
		site_id,
	)
	site_properties: dict[str, Any] = site_data.get("properties", {})
	site_name = site_properties.get("hs_object_id")

	# Add a comment on the CRM Deal to record the deployment site
	# _add_deal_comment(crm_deal_name, site_id_str, site_name, site_properties)

	# Create an ERPNext Project
	project = frappe.new_doc("Project")
	project.project_name = f"{site_name} - {crm_deal_name}"
	project.project_type = "Internal"

	project.custom_hubspot_deal_id= hubspot_deal_id_str
	project.custom_hubspot_deployment_site_id = site_id_str
	project.insert(ignore_permissions=True, ignore_mandatory=True)
	frappe.db.commit()

	frappe.logger("hubspot").info(
		f"Created Project {project.name} for deployment site {site_id_str} / deal {hubspot_deal_id_str}"
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
