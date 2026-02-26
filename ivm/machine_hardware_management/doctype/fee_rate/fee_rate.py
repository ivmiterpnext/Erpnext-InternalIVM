# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from ivm.ivm.utils.sync_util import sync_doctype_from_api


class FeeRate(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Fee Rate",
        api_type="icorp",
        endpoint="FeeRate",
        key_field="id",
        api_fields=["id", "amount", "is_active"]
    )
