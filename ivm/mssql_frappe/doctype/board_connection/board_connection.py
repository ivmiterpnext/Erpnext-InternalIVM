# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.mssql_frappe.utils.sync_util import sync_doctype_from_api

class BoardConnection(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Board Connection",
        api_type="icorp",
        endpoint="SV/BoardConnection",
        key_field="id",
        api_fields=["id", "name", "ip_address", "port"],
		field_map={"name": "connection_name"}
    )
