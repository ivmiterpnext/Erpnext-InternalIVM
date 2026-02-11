# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.machine_hardware_management.utils.sync_util import sync_doctype_from_api

class ClientLink(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Client Link",
        api_type="icorp",
        endpoint="Client?pageSize=9999&page=1",
        key_field="id",
        api_fields=["id", "name"],
		field_map={"name": "client_name"}
    )
