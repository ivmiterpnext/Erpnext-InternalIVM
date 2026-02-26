"""Auto-export customizations when they change in the UI"""
import json
import os
import frappe
from frappe.modules.utils import export_customizations

def auto_export_custom_field(doc, method):
    """Auto-export customizations for Custom Field and Property Setter on update only."""
    import frappe
    from frappe.modules.utils import export_customizations
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import or frappe.flags.in_sync_customizations:
        return
    if not frappe.conf.developer_mode:
        return
    if method == "on_update":
        doctype = doc.dt
        # Debounce: Only export once per doctype per request
        if not hasattr(frappe.local, "auto_exported_doctypes"):
            frappe.local.auto_exported_doctypes = set()
        if doctype in frappe.local.auto_exported_doctypes:
            return
        frappe.local.auto_exported_doctypes.add(doctype)
        export_customizations(module="IVM", doctype=doctype, sync_on_migrate=True, with_permissions=False)


def auto_export_property_setter(doc, method):
    import frappe
    from frappe.modules.utils import export_customizations
    if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_import or frappe.flags.in_sync_customizations:
        return
    if not frappe.conf.developer_mode:
        return
    if method == "on_update":
        doctype = doc.doc_type
        # Debounce: Only export once per doctype per request
        if not hasattr(frappe.local, "auto_exported_doctypes"):
            frappe.local.auto_exported_doctypes = set()
        if doctype in frappe.local.auto_exported_doctypes:
            return
        frappe.local.auto_exported_doctypes.add(doctype)
        export_customizations(module="IVM", doctype=doctype, sync_on_migrate=True, with_permissions=False)
