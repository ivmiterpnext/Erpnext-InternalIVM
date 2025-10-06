# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.sync_util import sync_doctype_from_api

class BoardFirmware(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Board Firmware",
        api_type="icorp",
        endpoint="SV/BoardFirmware?pageSize=999&page=1",
        key_field="id",
        api_fields=["id", "board_manufacturer_id", "version", "is_active", "comment"],
    )
