# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.mssql_frappe.utils.sync_util import sync_doctype_from_api

class MachineType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Machine Type",
        api_type="icorp",
        endpoint="SV/MachineType",
        key_field="id",
        api_fields=["id", "name", "is_active"],
		field_map={"name": "machine_type_name"}
    )
