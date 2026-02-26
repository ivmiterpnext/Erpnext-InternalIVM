"""Project creation flow for HubSpot-sourced won deals."""

from __future__ import annotations

from typing import Final

import frappe
from frappe.model.document import Document

HUBSPOT_SETTINGS_DOCTYPE: Final[str] = "HubSpot Settings"
CRM_DEAL_STATUS_DOCTYPE: Final[str] = "CRM Deal Status"
PROJECT_DOCTYPE: Final[str] = "Project"


def create_project_on_won(doc: Document, method: str | None = None) -> None:
	"""Create a Project exactly once when a CRM Deal transitions to Won."""
	if not _status_changed(doc):
		return

	if not _is_won_status(doc.get("status")):
		return

	if frappe.db.exists(PROJECT_DOCTYPE, {"crm_deal": doc.name}):
		return

	default_company = frappe.db.get_single_value(HUBSPOT_SETTINGS_DOCTYPE, "default_company")
	if not default_company:
		raise frappe.ValidationError("HubSpot Settings.default_company is required for Project creation.")

	project_name = _build_project_name(doc)

	project_doc = frappe.get_doc(
		{
			"doctype": PROJECT_DOCTYPE,
			"project_name": project_name,
			"company": default_company,
			"crm_deal": doc.name,
		}
	)

	try:
		project_doc.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="Failed creating Project for won CRM Deal",
			message={"crm_deal": doc.name, "status": doc.get("status")},
		)
		raise


def _status_changed(doc: Document) -> bool:
	if hasattr(doc, "has_value_changed"):
		return bool(doc.has_value_changed("status"))

	return False


def _is_won_status(status_name: str | None) -> bool:
	if not status_name:
		return False

	if not frappe.db.exists("DocType", CRM_DEAL_STATUS_DOCTYPE):
		return False

	status_type = frappe.db.get_value(CRM_DEAL_STATUS_DOCTYPE, status_name, "type")
	return isinstance(status_type, str) and status_type == "Won"


def _build_project_name(doc: Document) -> str:
	org_name = doc.get("organization_name") or doc.get("organization") or doc.name
	return f"{org_name} - {doc.name}"
