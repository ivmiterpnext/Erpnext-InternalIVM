# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.sync_util import sync_doctype_from_api

class MachineLink(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Machine Link",
        api_type="icorp",
        endpoint="SV/Machine?ActiveStatus=All&pageSize=99999&page=1",
        key_field="id",
        api_fields=["id", "name"],
		field_map={"name": "machine_name"}
    )

@frappe.whitelist()
def get_machine_name_from_machine_id(machine_id: str) -> str | None:
    name = frappe.db.get_value("Machine Link", machine_id, "machine_name")
    return name if name else "Unknown Machine"
