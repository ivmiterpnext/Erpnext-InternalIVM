# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from ivm.ivm.utils.api_utils import icorp_api_get

class AddressLink(Document):
	pass

def build_full_address(item):
    address_parts = [
        item.get("address_line_one"),
        item.get("address_line_two"),
        item.get("address_line_three"),
        item.get("address_line_four"),
        item.get("city"),
        item.get("state_code"),
        item.get("country_code"),
        item.get("postal_code")
    ]
    return ", ".join([p for p in address_parts if p])

@frappe.whitelist()
def sync():
    endpoint = "Address?pageSize=99999&page=1"
    data = icorp_api_get(endpoint)
    items = data.get("data", [])
    batch_size = 1000
    count = 0
    for item in items:
        full_address = build_full_address(item)
        doc_fields = {
            "doctype": "Address Link",
    		"id": str(item["id"]),
            "full_address": full_address
        }

        if frappe.db.exists("Address Link", item["id"]):
            frappe.db.set_value("Address Link", item["id"], "full_address", full_address)
        else:
            frappe.get_doc(doc_fields).insert(ignore_permissions=True)

        count += 1
        if count % batch_size == 0:
            frappe.db.commit()
    frappe.db.commit()
    return "Sync complete"
