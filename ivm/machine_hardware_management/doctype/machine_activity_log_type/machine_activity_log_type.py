# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.ivm.utils.sync_util import sync_doctype_from_api

class MachineActivityLogType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Machine Activity Log Type",
        api_type="icorp",
        endpoint="SV/MachineActivityLogType",
        key_field="code",
        api_fields=["id", "code", "description"]
    )
