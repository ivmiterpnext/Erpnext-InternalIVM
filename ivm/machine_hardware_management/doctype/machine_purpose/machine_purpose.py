# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.common.utils.sync_util import sync_doctype_from_api

class MachinePurpose(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Machine Purpose",
        api_type="icorp",
        endpoint="MachinePurpose",
        key_field="id",
        api_fields=["id", "description"]
    )
