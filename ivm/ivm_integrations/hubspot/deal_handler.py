from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client


def handle_deal_created(hubspot_deal_id: int | str) -> None:
	"""Create a CRM Deal from a newly created HubSpot deal.

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
	"""Handle a HubSpot deal moving to the closedwon stage.

	Updates the existing CRM Deal status to Won and triggers
	deployment site processing.

	Called asynchronously via frappe.enqueue from the webhook handler.
	"""
	try:
		crm_deal_name = _update_crm_deal_to_won(hubspot_deal_id)
		if crm_deal_name:
			from ivm.ivm_integrations.hubspot.deployment_site_handler import process_deployment_sites

			process_deployment_sites(hubspot_deal_id, crm_deal_name)
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

	# Idempotency check: skip if a CRM Deal with this HubSpot ID already exists
	if frappe.db.exists("CRM Deal", {"custom_hubspot_deal_id": hubspot_deal_id_str}):
		frappe.log_error(
			title=f"HubSpot: CRM Deal already exists for deal {hubspot_deal_id_str}",
			message="Skipping duplicate deal creation.",
		)
		return None

	# Fetch deal details from HubSpot
	hubspot_data = hubspot_client.get_deal(hubspot_deal_id)
	properties: dict[str, Any] = hubspot_data.get("properties", {})

	deal = frappe.new_doc("CRM Deal")
	deal.update(
		{
			"custom_hubspot_deal": hubspot_deal_id_str,
			# "last_response_time": hubspot_data.get("updatedAt"),
			# "organization_name": properties.get("dealname"),
			"deal_value": _parse_amount(properties.get("amount")),
			"status": "Qualification",
			"custom_hubspot_deal_name":properties.get("dealname")
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


def _parse_amount(value: Any) -> float:
	"""Safely parse a deal amount to a float, defaulting to 0."""
	if value is None:
		return 0.0
	try:
		return float(value)
	except (ValueError, TypeError):
		return 0.0
