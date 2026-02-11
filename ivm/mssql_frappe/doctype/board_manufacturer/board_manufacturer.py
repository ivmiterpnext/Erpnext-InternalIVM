# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.mssql_frappe.utils.sync_util import sync_doctype_from_api

class BoardManufacturer(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Board Manufacturer",
        api_type="icorp",
        endpoint="SV/BoardManufacturer",
        key_field="id",
        api_fields=["id", "name", "is_active"],
        field_map={"name": "manufacturer_name"}
    )
