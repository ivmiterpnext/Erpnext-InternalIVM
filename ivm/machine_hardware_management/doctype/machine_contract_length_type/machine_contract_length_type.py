# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.machine_hardware_management.utils.sync_util import sync_doctype_from_api

class MachineContractLengthType(Document):
	pass

@frappe.whitelist()
def sync():
    frappe.only_for("System Manager")
    return sync_doctype_from_api(
        doctype="Machine Contract Length Type",
        api_type="icorp",
        endpoint="MachineContractLengthType",
        key_field="id",
        api_fields=["id", "name"],
        field_map={"name": "contract_length_name"}
    )
