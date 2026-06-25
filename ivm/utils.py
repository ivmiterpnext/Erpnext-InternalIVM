import frappe


@frappe.whitelist()
def get_child_table_row(doctype: str, name: str) -> dict:
    """
    Fetch a single child table row as a dict.
    Needed because child table records (istable=1) are not served via the
    standard frappe.model.with_doc / frappe.get_doc client API.
    """
    meta = frappe.get_meta(doctype)
    if not meta.istable:
        frappe.throw(f"{doctype} is not a child table DocType.")
    row = frappe.get_doc(doctype, name)
    return row.as_dict()
