# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.sync_util import sync_doctype_from_api
from mssql_frappe.utils.azure_api_utils import API_BASE_URL

class BoardFirmware(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Board Firmware",
        api_url=f"{API_BASE_URL}/BoardFirmware?pageSize=999&page=1",
        key_field="id",
        api_fields=["board_manufacturer_id", "version", "is_active", "comment"],
    )