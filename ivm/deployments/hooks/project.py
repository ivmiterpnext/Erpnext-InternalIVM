from frappe.utils import getdate, add_days
from ivm.deployments.utils.date_calculations import (
    get_provide_planogram_base_date,
    calculate_days,
    user_and_restriction_requirements_due,
)


def before_validate(doc, method=None):
    doc._original_status = doc.status


def validate(doc, method=None):
    # ERPNext's validate() -> update_percent_complete() resets status to Open/Completed.
    # Restore it if the user had set a custom status.
    if getattr(doc, "_original_status", None) not in ("Open", "Completed", "Cancelled", None):
        doc.status = doc._original_status

    _update_provide_planogram_due_date(doc)
    _update_approve_planogram_and_locker_config_due(doc)
    _update_pog_created_in_database_due(doc)
    _update_sample_products_due(doc)
    _update_delivery_and_install_contact_due(doc)
    _update_install_checklist_due(doc)


def after_insert(doc, method=None):
    from ivm.deployments.services.create_machines_from_project import create_machines_from_project
    create_machines_from_project(doc)


def _update_install_checklist_due(doc):
    doc.install_checklist_due = doc.approve_travel_cost_due


def _update_provide_planogram_due_date(doc):
    if not doc.placement_agreement:
        doc.provide_planogram_due = None
        return
    base_days = 7 if doc.expedited_delivery else (17 if doc.locale == "Domestic" else 23)
    added_days = int(doc.added_days) if doc.added_days else 0
    doc.provide_planogram_due = get_provide_planogram_base_date(doc.placement_agreement, base_days, added_days)


def _update_approve_planogram_and_locker_config_due(doc):
    if not doc.placement_agreement:
        doc.approve_planogram_and_locker_config_due = None
        return
    base_days = 11 if doc.expedited_delivery else (24 if doc.locale == "Domestic" else 27)
    added_days = int(doc.added_days) if doc.added_days else 0
    doc.approve_planogram_and_locker_config_due = get_provide_planogram_base_date(doc.placement_agreement, base_days, added_days)


def _update_pog_created_in_database_due(doc):
    if not doc.placement_agreement:
        doc.pog_created_in_database_due = None
        return
    base_days = 10 if doc.expedited_delivery else (25 if doc.locale == "Domestic" else 31)
    added_days = int(doc.added_days) if doc.added_days else 0
    doc.pog_created_in_database_due = get_provide_planogram_base_date(doc.placement_agreement, base_days, added_days)


def _update_sample_products_due(doc):
    if not doc.placement_agreement:
        doc.sample_products_due = ""
        doc.sample_badge_due = ""
        return
    base_days = 2 if doc.expedited_delivery else (7 if doc.locale == "Domestic" else 13)
    added_days = int(doc.added_days) if doc.added_days else 0
    due_date = get_provide_planogram_base_date(doc.placement_agreement, base_days, added_days)
    doc.sample_products_due = due_date
    doc.sample_badge_due = due_date


def _update_delivery_and_install_contact_due(doc):
    if not doc.placement_agreement:
        doc.graphic_design_approval_due = ""
        doc.delivery_and_install_contact_due_customs = ""
        doc.delivery_install_and_coi_requirements = ""
        doc.user_and_restriction_requirements_due = ""
        return

    ur_due = user_and_restriction_requirements_due(doc.placement_agreement, doc.added_days, doc.expedited_delivery)
    weekday = getdate(doc.placement_agreement).weekday()

    if doc.expedited_delivery:
        due_days = add_days(doc.placement_agreement, calculate_days(int(doc.added_days), weekday, 9))
        doc.graphic_design_approval_due = due_days
        doc.delivery_and_install_contact_due_customs = due_days
        doc.delivery_install_and_coi_requirements = due_days
        doc.user_and_restriction_requirements_due = ur_due
    else:
        due_days = add_days(doc.placement_agreement, calculate_days(int(doc.added_days), weekday, 10))
        doc.delivery_and_install_contact_due_customs = due_days
        doc.delivery_install_and_coi_requirements = due_days
        doc.user_and_restriction_requirements_due = ur_due
        doc.graphic_design_approval_due = add_days(doc.placement_agreement, calculate_days(int(doc.added_days), weekday, 20))
