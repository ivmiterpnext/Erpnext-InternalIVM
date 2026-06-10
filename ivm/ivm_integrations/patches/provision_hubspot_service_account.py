"""
Provision the HubSpot integration service account, role, and permissions.

Creates the Integration role, grants it create/read/write on the DocTypes
used by the HubSpot webhook handlers, and creates the service account user.
"""

import frappe
from ivm.ivm_integrations.hubspot.constants import HUBSPOT_ROLE, HUBSPOT_USER

_PERMITTED_DOCTYPES: list[str] = [
    "CRM Deal",
    "CRM Organization",
    "Contact",
    "Address",
    "Deployment Location",
    "FCRM Note",
    "CRM Task",
    "CRM Call Log",
    "Communication",
    "File",
]


def execute() -> None:
    _ensure_integration_role()
    _ensure_role_permissions()
    _ensure_hubspot_user()

def _ensure_integration_role() -> None:
    """Create the Integration role if it does not already exist."""

    if frappe.db.exists("Role", HUBSPOT_ROLE):
        return

    role = frappe.new_doc("Role")
    role.role_name = HUBSPOT_ROLE
    role.desk_access = 1
    role.is_custom = 1
    role.insert(ignore_permissions=True)
    print(f"  Created role '{HUBSPOT_ROLE}'")

def _ensure_role_permissions() -> None:
    """Grant the Integration role create/read/write on required DocTypes."""

    for doctype in _PERMITTED_DOCTYPES:
        exists = frappe.db.exists("Custom DocPerm", {
            "parent": doctype,
            "role": HUBSPOT_ROLE,
        })
        if exists:
            continue

        perm = frappe.new_doc("Custom DocPerm")
        perm.parent = doctype
        perm.parenttype = "DocType"
        perm.parentfield = "permissions"
        perm.role = HUBSPOT_ROLE
        perm.permlevel = 0
        perm.read = 1
        perm.write = 1
        perm.create = 1
        perm.insert(ignore_permissions=True)
        print(f"  Granted {HUBSPOT_ROLE} permissions on {doctype}")

def _ensure_hubspot_user() -> None:
    """Create the HubSpot service account if it does not already exist."""
    
    if frappe.db.exists("User", HUBSPOT_USER):
        return

    user = frappe.new_doc("User")
    user.email = HUBSPOT_USER
    user.first_name = "HubSpot"
    user.last_name = "Integration"
    user.user_type = "System User"
    user.send_welcome_email = 0
    user.enabled = 1

    user.append("roles", {"role": HUBSPOT_ROLE})

    user.insert(ignore_permissions=True)
    print(f"  Created HubSpot service user '{HUBSPOT_USER}'")
