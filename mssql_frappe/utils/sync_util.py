import frappe
from mssql_frappe.utils.azure_api_utils import azure_api_get

def sync_doctype_from_api(doctype, api_url, key_field, api_fields):
    try:
        frappe.logger().info(f"Syncing {doctype} from api")

        data = azure_api_get(api_url)
        items = data.get("data", [])

        for item in items:
            filters = { "name": item[key_field] }
            docs = frappe.get_all(doctype, filters=filters, fields=["*"])
            print(item)
            if docs:
                doc = docs[0]
                updated_fields = {}
                for key in api_fields:
                    api_value = str(item.get(key)).strip()
                    doc_value = str(doc.get(key)).strip()
                    if doc_value != api_value:
                        updated_fields[key] = item.get(key)

                if updated_fields:
                    frappe.db.set_value(doctype, item[key_field], updated_fields)
                    if updated_fields:
                        frappe.logger().info(f"Updated {item[key_field]}: {updated_fields}")
                    else:
                        frappe.logger().info(f"No changes for {item[key_field]}")

            else:
                new_doc = frappe.get_doc({
                    "doctype": doctype,
                    "name": item[key_field],
                    **item
                })

                new_doc.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), f"{doctype}.sync error")

    return "Sync complete"