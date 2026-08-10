import frappe


def on_update(doc, method):
    frappe.db.set_value(
        doc.doctype,
        doc.name,
        {
            "created_date": doc.creation,
            "custom_modified_date": doc.modified,
            "custom_created_by": doc.owner,
            "custom_modified_by": doc.modified_by,
        },
        update_modified=False,
    )
    doc.reload()
