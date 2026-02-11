import frappe
from frappe.model.document import Document
from ivm.mssql_frappe.utils.sync_util import sync_doctype_from_api

class SmartScreenConfiguration(Document):
	pass

@frappe.whitelist()
def sync():
    return sync_doctype_from_api(
        doctype="Smart Screen Configuration",
        api_type="headwind",
        endpoint="private/configurations/search",
        key_field="id",
        api_fields=["id", "name"],
		field_map={"name": "config_name"}
    )
