# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.mssql_frappe.utils.sync_util import sync_doctype_from_api

class BoardType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Board Type",
        api_type="icorp",
        endpoint="SV/BoardType",
        key_field="code",
        api_fields=["id", "code", "description"]
    )
