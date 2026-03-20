from frappe.model.utils.rename_field import rename_field

def execute():
    renames = {
        # "DocType": [
        #     ("old_field", "new_field"),
        # ],

        "Project": [ # Deployment
            ("wrap_layout", "legacy_wrap_layout"),
            ("wrap_type", "legacy_wrap_type"),
            # ...
        ],
    }

    try:
        for doctype, fields in renames.items():
            for old_field, new_field in fields:
                if frappe.db.has_column(doctype, old_field):
                    frappe.logger().info(
                        f"Renaming field '{old_field}' to '{new_field}' in {doctype}"
                    )
                    rename_field(doctype, old_field, new_field)
                    frappe.logger().info(
                        f"Successfully renamed field '{old_field}' to '{new_field}' in {doctype}"
                    )
                else:
                    frappe.logger().info(
                        f"Field '{old_field}' does not exist in {doctype}, skipping"
                    )
    except Exception:
        frappe.log_error(
            title=f"Field Rename Patch Failed",
            message=frappe.get_traceback(),
        )
        raise
