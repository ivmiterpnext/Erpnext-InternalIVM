# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.sync_util import sync_doctype_from_api
from mssql_frappe.utils.azure_api_utils import API_BASE_URL

class HardwareAvailabilityType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Hardware Availability Type",
        api_url=f"{API_BASE_URL}/HardwareAvailabilityType",
        key_field="code",
        api_fields=["id", "code", "description"]
    )