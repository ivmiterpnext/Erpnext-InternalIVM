# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.machine_hardware_management.utils.sync_util import sync_doctype_from_api

class Timezone(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Timezone",
        api_type="icorp",
        endpoint="TimeZone",
        key_field="id",
        api_fields=["id", "display_name", "iana_timezone", "supports_daylight_savings_time"]
    )
