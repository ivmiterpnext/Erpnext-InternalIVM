import frappe
from frappe.model.document import Document
from ivm.machine_hardware_management.utils.sync_util import sync_doctype_from_api

class SmartScreenGroup(Document):
	pass

@frappe.whitelist()
def sync():
    frappe.only_for("System Manager")
    return sync_doctype_from_api(
        doctype="Smart Screen Group",
        api_type="headwind",
        endpoint="private/groups/search",
        key_field="id",
        api_fields=["id", "name"],
		field_map={"name": "group_name"}
    )
