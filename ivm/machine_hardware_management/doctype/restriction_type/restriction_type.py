# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from ivm.machine_hardware_management.utils.sync_util import sync_doctype_from_api

class RestrictionType(Document):
	pass

@frappe.whitelist()
def sync():
    frappe.only_for("System Manager")
    return sync_doctype_from_api(
        doctype="Restriction Type",
        api_type="icorp",
        endpoint="RestrictionType",
        key_field="id",
        api_fields=["id", "code", "description", "is_active"]
    )
