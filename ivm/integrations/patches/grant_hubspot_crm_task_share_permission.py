"""
Grant the HubSpot Integration role 'share' permission on CRM Task.

provision_hubspot_service_account granted read/write/create on CRM Task
but not share. CRM Task.after_insert() (crm app) calls assign_to() via
the public frappe.desk.form.assign_to.add() wrapper, which always
enforces a share-permission check on the acting session user regardless
of the ignore_permissions=True passed to doc.insert() — unlike CRM Deal/
CRM Lead, whose controllers bypass this via the internal _add(...,
ignore_permissions=True). Without share=1, hubspot@ivm.local's CRM Task
inserts fail (and roll back) the moment a hubspot_owner_id is resolved
and assigned_to is set.
"""
import frappe
from ivm.integrations.hubspot.constants import HUBSPOT_ROLE

def execute() -> None:
    name = frappe.db.get_value(
        "Custom DocPerm", {"parent": "CRM Task", "role": HUBSPOT_ROLE}, "name"
    )
    if not name:
        return
    if frappe.db.get_value("Custom DocPerm", name, "share"):
        return
    frappe.db.set_value("Custom DocPerm", name, "share", 1)
    frappe.clear_cache()
