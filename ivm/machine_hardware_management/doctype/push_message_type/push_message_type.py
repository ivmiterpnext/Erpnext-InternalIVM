# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.common.utils.sync_util import sync_doctype_from_api


class PushMessageType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Push Message Type",
        api_type="icorp",
        endpoint="SV/PushMessageType",
        key_field="payload",
        api_fields=["id", "payload", "description"]
    )
