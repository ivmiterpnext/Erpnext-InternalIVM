"""
Event handlers for Project documents.
"""

import frappe
from frappe.model.document import Document

from ivm.deployments.utils.date_calculations import add_business_days

# Each tuple: (field_name, expedited_days, domestic_days, international_days)
_DUE_DATE_RULES: list[tuple[str, int, int, int]] = [
	("provide_planogram_due", 7, 17, 23),
	("approve_planogram_and_locker_config_due", 11, 24, 27),
	("pog_created_in_database_due", 10, 25, 31),
	("sample_products_due", 2, 7, 13),
	("sample_badge_due", 2, 7, 13),
	("delivery_and_install_contact_due_customs", 9, 10, 10),
	("delivery_install_and_coi_requirements", 9, 10, 10),
	("user_and_restriction_requirements_due", 14, 20, 20),
	("graphic_design_approval_due", 9, 20, 20),
]

_DEPLOYMENT_DETAIL_TABLES: list[str] = [
	"custom_deployment_smartstation_details",
	"custom_deployment_smartlocker_details",
	"custom_deployment_smartsync_details",
	"custom_deployment_smartvault_details",
	"custom_deployment_smartcenter_details",
]


def before_validate(doc: Document, method: str | None = None) -> None:
	"""Snapshot the current status before ERPNext's validate overwrites it."""
	doc._original_status = doc.status


def validate(doc: Document, method: str | None = None) -> None:
	"""Restore custom status and recalculate due dates."""
	# ERPNext's validate() -> update_percent_complete() resets status to Open/Completed.
	# Restore it if the user had set a custom status.
	if getattr(doc, "_original_status", None) not in ("Open", "Completed", "Cancelled", None):
		doc.status = doc._original_status

	_link_crm_deal(doc)
	_update_due_dates(doc)
	_update_install_checklist_due(doc)
	_require_customer_for_deployment(doc)
	_validate_icorp_client_id(doc)


def after_insert(doc: Document, method: str | None = None) -> None:
	"""Provision machine records from the newly created project."""
	from ivm.deployments.services.create_machines_from_project import create_machines_from_project

	create_machines_from_project(doc)


def _require_customer_for_deployment(doc: Document) -> None:
	"""A Deployment Project must name its Customer before it is saved by a user.

	System inserts (create_projects_from_deal) pass ignore_mandatory=True and are exempt."""
	if doc.project_type == "Deployment" and not doc.customer and not doc.flags.ignore_mandatory:
		frappe.throw("Select the Customer for this deployment before saving.")


def _link_crm_deal(doc: Document) -> None:
	if not doc.custom_hubspot_deal_id or doc.custom_crm_deal:
		return
	deal = frappe.db.get_value("CRM Deal", {"custom_hubspot_deal_id": doc.custom_hubspot_deal_id}, "name")
	if deal:
		doc.custom_crm_deal = deal


def _get_added_days(doc: Document) -> int:
	"""Return the added_days field as an integer, defaulting to 0."""
	return int(doc.added_days) if doc.added_days else 0


def _update_install_checklist_due(doc: Document) -> None:
	"""Mirror the install checklist due date from the approve travel cost due date."""
	doc.install_checklist_due = doc.approve_travel_cost_due


def _safe_due_date(date, business_days) -> str | None:
	"""Compute a due date, logging and returning None instead of raising on failure."""
	try:
		return add_business_days(date, business_days)
	except Exception:
		frappe.log_error(
			title="Due-date calculation failed",
			message=frappe.get_traceback(with_context=True),
		)
		return None


def _update_due_dates(doc: Document) -> None:
	"""Recalculate all rule-driven due dates from the placement agreement."""

	added_days = _get_added_days(doc)

	for field, expedited_days, domestic_days, international_days in _DUE_DATE_RULES:
		if not doc.placement_agreement:
			doc.set(field, None)
			continue

		base_days = (
			expedited_days
			if doc.expedited_delivery
			else (domestic_days if doc.locale == "Domestic" else international_days)
		)
		doc.set(field, _safe_due_date(doc.placement_agreement, base_days + added_days))


def _no_deployable_client_message(customer: str) -> str:
	"""Explain why a Customer has no selectable iCorp client: inactive-only clients
	(reactivate, or create new) vs no client at all (link or create one)."""
	from ivm.deployments.services.deployment_clients import _customer_client_summary

	customer_link = frappe.utils.get_link_to_form("Customer", customer)
	tab_href = frappe.utils.escape_html(frappe.utils.get_url_to_form("Customer", customer) + "#icorp_tab")
	tab_link = f'<a href="{tab_href}">Customer\'s iCorp tab</a>'
	summary = _customer_client_summary(customer)
	if summary["inactive"] and not summary["active"]:
		return (
			f"{customer_link} only has inactive iCorp clients ({', '.join(summary['inactive'])}). "
			"Reactivate one in iCorp (the daily sync will pick it up), or add one on the "
			f"{tab_link}, then pick it here."
		)
	return f"{customer_link} has no iCorp client yet. Add one on the {tab_link}, then pick it here."


def _validate_icorp_client_id(doc: Document) -> None:
	"""Validate and resolve Project.icorp_client_id / partner_customer for
	Deployment Projects. Strict checks only run on a new Project, when
	customer or icorp_client_id changed, or when stage just left
	"Waiting Assignment" with no client set -- so legacy Projects that
	predate this field can still be saved untouched."""
	from ivm.deployments.services.deployment_clients import (
		_deployable_clients,
		derive_partner,
		derive_partner_client,
	)

	if doc.project_type != "Deployment":
		return

	stage_before = None
	if not doc.is_new():
		stage_before = frappe.db.get_value("Project", doc.name, "stage")

	stage_left_waiting = (
		stage_before == "Waiting Assignment" and doc.stage != "Waiting Assignment" and not doc.icorp_client_id
	)

	strict = (
		doc.is_new()
		or doc.has_value_changed("customer")
		or doc.has_value_changed("icorp_client_id")
		or stage_left_waiting
	)

	_sync_row_icorp_clients(doc)

	if strict and doc.customer:
		candidates = _deployable_clients(doc.customer)
		by_name = {c["name"]: c for c in candidates}

		if not doc.icorp_client_id:
			if doc.flags.ignore_mandatory:
				return
			if not candidates:
				frappe.throw(_no_deployable_client_message(doc.customer))
			frappe.throw("Select the iCorp Client for this deployment.")

		chosen = by_name.get(doc.icorp_client_id)
		if chosen and chosen["group"] == "managed":
			doc.partner_customer = doc.customer
			doc.customer = chosen["customer"]
		elif not chosen:
			link_customer = frappe.db.get_value("iCorp Client Link", doc.icorp_client_id, "customer")
			if link_customer != doc.customer:
				frappe.throw(
					f"iCorp Client {doc.icorp_client_id} does not belong to Customer {doc.customer}."
				)

		for table in _DEPLOYMENT_DETAIL_TABLES:
			for row in doc.get(table) or []:
				row_client = row.get("icorp_client_id")
				if not row_client:
					continue
				row_customer = frappe.db.get_value("iCorp Client Link", row_client, "customer")
				if row_customer != doc.customer:
					frappe.throw(
						f"Row '{row.get('machine_name') or row.name}' in {table}: "
						f"iCorp Client {row_client} does not belong to Customer {doc.customer}."
					)

	if doc.icorp_client_id:
		partner = derive_partner(doc.icorp_client_id)
		if partner:
			doc.partner_customer = partner
			doc.partner_icorp_client_id = derive_partner_client(doc.icorp_client_id)


def _sync_row_icorp_clients(doc: Document) -> None:
	"""Machine detail rows default to the Project's icorp_client_id. Rows that
	are blank, or still hold the Project's previous client, follow the
	Project's current client. Rows manually set to a different client are
	left alone."""
	before = None if doc.is_new() else doc.get_doc_before_save()
	previous = before.get("icorp_client_id") if before else None
	current = doc.icorp_client_id
	for table in _DEPLOYMENT_DETAIL_TABLES:
		for row in doc.get(table) or []:
			row_client = row.get("icorp_client_id")
			if not row_client or (previous and row_client == previous):
				row.icorp_client_id = current
