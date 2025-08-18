# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.azure_api_utils import azure_api_get

class HardwareAvailabilityType(Document):
	pass

@frappe.whitelist()
def sync():
    try:
        url = "https://dev.icorpapi.ivminc.com/SV/HardwareAvailabilityType"
        data = azure_api_get(url)
        items = data.get("data", [])

        for item in items:
            docs = frappe.get_all("Hardware Availability Type", filters={"name": item["code"]}, fields=["*"])
            if docs:
                doc = docs[0]
                updated_fields = {}

                api_fields = ["id", "code", "description"]

                for key in api_fields:
                    api_value = str(item.get(key)).strip()
                    doc_value = str(doc.get(key)).strip()
                    if doc_value != api_value:
                        updated_fields[key] = item.get(key)

                # Only update if there are actual changes
                if updated_fields:
                    frappe.db.set_value("Hardware Availability Type", item["code"], updated_fields)
                    print(f"Updated {item['code']}: {updated_fields}")
                else:
                    print(f"No changes for {item['code']}")
            else:
                new_doc = frappe.get_doc({
                    "doctype": "Hardware Availability Type",
                    "name": item["code"],
                    **item  # Unpack all fields from the API object
                })

                new_doc.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), "HardwareAvailabilityType.sync error")

    return "Sync complete"
