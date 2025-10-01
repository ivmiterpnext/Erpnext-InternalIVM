# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.sync_util import sync_doctype_from_api

class LocationLink(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Location Link",
        api_type="icorp",
        endpoint="SV/Location?pageSize=9999&page=1",
        key_field="id",
        api_fields=["id", "name", "client_id"],
		field_map={"name": "location_name"}
    )
