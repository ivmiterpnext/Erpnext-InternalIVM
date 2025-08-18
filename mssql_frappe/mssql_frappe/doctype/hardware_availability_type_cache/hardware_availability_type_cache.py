# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe.model.document import Document
from mssql_frappe.mssql_frappe.doctype.hardware_availability_type.hardware_availability_type import get_hardware_availability_type_list

class HardwareAvailabilityTypeCache(Document):
	pass


@frappe.whitelist()
def run_hardware_availability_type_cache_sync():
    items = get_hardware_availability_type_list()
    for item in items:
        doc = frappe.get_all("Hardware Availability Type Cache", filters={"name": item["code"]})
        if doc:
            frappe.db.set_value("Hardware Availability Type Cache", item["code"], "description", item["description"])
        else:
            new_doc = frappe.get_doc({
                "doctype": "Hardware Availability Type Cache",
                "name": item["code"],
                "code": item["code"],
                "description": item["description"],
                "id": item.get("id")
            })
            new_doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return "Sync complete"