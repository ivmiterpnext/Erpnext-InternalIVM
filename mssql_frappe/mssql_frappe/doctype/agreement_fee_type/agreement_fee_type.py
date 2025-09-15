# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.sync_util import sync_doctype_from_api

class AgreementFeeType(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Agreement Fee Type",
        api_type="icorp",
        endpoint=f"AgreementFeeType",
        key_field="code",
        api_fields=["id", "code", "description", "is_active", "is_client", "is_vendor", "is_machine", 
                    "fee_rate_type_id", "fee_rate_type_code", "fee_rate_type_description"]
    )