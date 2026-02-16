# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from ivm.common.utils.sync_util import sync_doctype_from_api

class CheckFrequencyType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Check Frequency Type",
        api_type="icorp",
        endpoint="CheckFrequencyType",
        key_field="code",
        api_fields=["id", "code", "description"]
    )
