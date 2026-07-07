"""
Event handlers for Project documents.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, getdate

from ivm.deployments.utils.date_calculations import (
    calculate_days,
    get_provide_planogram_base_date,
    user_and_restriction_requirements_due,
)

# Each tuple: (field_name, expedited_days, domestic_days, international_days)
_DUE_DATE_RULES: list[tuple[str, int, int, int]] = [
    ("provide_planogram_due",                     7,  17, 23),
    ("approve_planogram_and_locker_config_due",  11,  24, 27),
    ("pog_created_in_database_due",              10,  25, 31),
    ("sample_products_due",                       2,   7, 13),
    ("sample_badge_due",                          2,   7, 13),
]


def before_validate(doc: Document, method: str | None = None) -> None:
    """Snapshot the current status before ERPNext's validate overwrites it."""
    doc._original_status = doc.status

def validate(doc: Document, method: str | None = None) -> None:
    """Restore custom status and recalculate milestone due dates."""
    # ERPNext's validate() -> update_percent_complete() resets status to Open/Completed.
    # Restore it if the user had set a custom status.
    if getattr(doc, "_original_status", None) not in ("Open", "Completed", "Cancelled", None):
        doc.status = doc._original_status

    _link_crm_deal(doc)
    _update_milestone_due_dates(doc)
    _update_delivery_and_install_contact_due(doc)
    _update_install_checklist_due(doc)

def after_insert(doc: Document, method: str | None = None) -> None:
    """Provision machine records from the newly created project."""
    from ivm.deployments.services.create_machines_from_project import create_machines_from_project
    create_machines_from_project(doc)

def _link_crm_deal(doc: Document) -> None:
    if not doc.custom_hubspot_deal_id or doc.custom_crm_deal:
        return
    deal = frappe.db.get_value(
        "CRM Deal", {"custom_hubspot_deal_id": doc.custom_hubspot_deal_id}, "name"
    )
    if deal:
        doc.custom_crm_deal = deal


def _get_added_days(doc: Document) -> int:
    """Return the added_days field as an integer, defaulting to 0."""
    return int(doc.added_days) if doc.added_days else 0

def _update_install_checklist_due(doc: Document) -> None:
    """Mirror the install checklist due date from the approve travel cost due date."""
    doc.install_checklist_due = doc.approve_travel_cost_due

def _update_milestone_due_dates(doc: Document) -> None:
    """Recalculate all rule-driven milestone due dates from the placement agreement."""

    added_days = _get_added_days(doc)

    for field, expedited, domestic, international in _DUE_DATE_RULES:
        if not doc.placement_agreement:
            doc.set(field, None)
            continue

        base_days = expedited if doc.expedited_delivery else (domestic if doc.locale == "Domestic" else international)
        doc.set(field, get_provide_planogram_base_date(doc.placement_agreement, base_days, added_days))

def _update_delivery_and_install_contact_due(doc: Document) -> None:
    """Recalculate delivery, install contact, and graphic design due dates."""

    if not doc.placement_agreement:
        doc.graphic_design_approval_due = ""
        doc.delivery_and_install_contact_due_customs = ""
        doc.delivery_install_and_coi_requirements = ""
        doc.user_and_restriction_requirements_due = ""
        return

    added_days = _get_added_days(doc)
    weekday = getdate(doc.placement_agreement).weekday()

    contact_base = 9 if doc.expedited_delivery else 10
    due_days = add_days(doc.placement_agreement, calculate_days(added_days, weekday, contact_base))
    doc.delivery_and_install_contact_due_customs = due_days
    doc.delivery_install_and_coi_requirements = due_days
    doc.user_and_restriction_requirements_due = user_and_restriction_requirements_due(
        doc.placement_agreement, doc.added_days, doc.expedited_delivery,
    )

    graphic_base = contact_base if doc.expedited_delivery else 20
    doc.graphic_design_approval_due = add_days(
        doc.placement_agreement, calculate_days(added_days, weekday, graphic_base),
    )
