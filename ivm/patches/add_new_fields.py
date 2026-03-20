import frappe

def execute():
    new_fields = {
        # "DocType": [
        #     {
        #         "fieldname": "new_field",
        #         "fieldtype": "Data",
        #         "label": "New Field",
        #     },
        # ],

        "Project": [
            {
                "fieldname": "new_field_1",
                "fieldtype": "Data",
                "label": "New Field 1",
            },
            {
                "fieldname": "new_field_2",
                "fieldtype": "Select",
                "label": "New Field 2",
                "options": "\nOption A\nOption B\nOption C",
            },
        ],
    }

    for doctype, fields in new_fields.items():
        for field in fields:
            if not frappe.db.has_column(doctype, field["fieldname"]):
                frappe.logger().info(f"Adding field '{field['fieldname']}' to {doctype}")
                frappe.db.add_column(
                    doctype,
                    field["fieldname"],
                    frappe.db.get_column_type(field["fieldtype"], field.get("options")),
                )
                frappe.logger().info(f"Successfully added field '{field['fieldname']}' to {doctype}")
            else:
                frappe.logger().info(f"Field '{field['fieldname']}' already exists in {doctype}, skipping")


