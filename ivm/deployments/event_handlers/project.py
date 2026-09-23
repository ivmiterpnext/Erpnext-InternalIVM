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


def after_insert(doc: Document, method: str | None = None) -> None:
	"""Provision machine records from the newly created project."""
	from ivm.deployments.services.create_machines_from_project import create_machines_from_project

	create_machines_from_project(doc)


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
