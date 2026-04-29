import frappe


def sync_doctype_from_api(doctype, api_type, endpoint, key_field, api_fields, field_map=None):
    from ivm.machine_hardware_management.utils.api_utils import headwind_api_request, icorp_api_get
    try:
        frappe.logger().info(f"Syncing {doctype}")
        if api_type == "headwind":
            data = headwind_api_request("GET", endpoint)
        elif api_type == "icorp":
            print("Testing the catch here")
            data = icorp_api_get(endpoint)
        else:
            frappe.logger().error(f"Unknown api_type: {api_type}")
            return f"Unknown api_type: {api_type}"

        items = data.get("data", [])

        for item in items:
            filters = { "name": item[key_field] }
            docs = frappe.get_all(doctype, filters=filters, fields=["*"])

            if docs:
                doc = docs[0]
                updated_fields = {}

                for key in api_fields:
                    frappe_field = field_map[key] if field_map and key in field_map else key
                    api_value = str(item.get(key)).strip()
                    doc_value = str(doc.get(frappe_field)).strip()
                    if doc_value != api_value:
                        updated_fields[frappe_field] = item.get(key)

                if updated_fields:
                    frappe.db.set_value(doctype, item[key_field], updated_fields)
                    frappe.logger().info("Updated %s: %s", item[key_field], updated_fields)
                else:
                    frappe.logger().info("No changes for %s", item[key_field])

            else:
                doc_fields = {
                    "doctype": doctype,
                    "name": item[key_field]
                }

                for key in api_fields:
                    frappe_field = field_map[key] if field_map and key in field_map else key
                    doc_fields[frappe_field] = item.get(key)

                new_doc = frappe.get_doc(doc_fields)
                new_doc.insert(ignore_permissions=True)
        frappe.db.commit()

    except Exception:
        frappe.log_error(frappe.get_traceback(), f"{doctype}.sync error")

    return "Sync complete"
