import frappe
from frappe import _


@frappe.whitelist()
def get_child_tasks(parent_task):
    if (parent_task != ""):
        return [frappe.db.get_list('Task', filters={'parent_task': parent_task}, fields=['name', 'subject'])]


def get_data(data):
    return {
        "fieldname": "issue",
        "non_standard_fieldnames": {"Warehouse Request": "related_case", "Issue": "parent_case"},
        "transactions": [
            {"label": _("Activity"), "items": ["Task"]},
            {"label": _("Warehouse Request"), "items": ["Warehouse Request"]},
            {"label": _("Related Cases"), "items": ["Issue"]}]}


@frappe.whitelist()
def get_issue_type_record(record_name):
    doc = frappe.get_doc("Issue Type", record_name)
    return doc.as_dict()


@frappe.whitelist()
def get_connectivity_type_record(record_name):
    doc = frappe.get_doc("Connectivity Type", record_name)
    return doc.as_dict()


@frappe.whitelist()
def get_case_sub_reason_options(case_reason):
    if case_reason == "":
        return []
    doc = frappe.get_doc("Case Reason", case_reason)
    child_table_records = doc.get("case_sub_reason")
    child_field_values = [child_record.get(
        "case_sub_reason") for child_record in child_table_records]
    return child_field_values


@frappe.whitelist()
def get_contact_name(doctype, txt, searchfield, start, page_len, filters):
    names = filters.get('name')
    if names == "":
        return []
    list_of_records = frappe.db.sql("""SELECT DISTINCT c.name
        FROM `tabContact` c
        INNER JOIN `tabDynamic Link` dl ON c.name = dl.parent
        WHERE dl.link_doctype = 'Customer' AND dl.link_title = %s """, (names,))

    return list_of_records


@frappe.whitelist()
def override_project_dashboard(data):
    return {
        "heatmap": True,
        "heatmap_message": _("This is based on the Time Sheets created against this project"),
        "fieldname": "project",
        "non_standard_fieldnames": {"Warehouse Request": "related_project"},
        "transactions": [
            {
                "label": _("Project"),
                "items": ["Task", "Timesheet", "Issue", "Project Update"],
            },
            {"label": _("Material"), "items": [
                "Material Request", "BOM", "Stock Entry"]},
            {"label": _("Sales"), "items": [
                "Sales Order", "Delivery Note", "Sales Invoice"]},
            {"label": _("Purchase"), "items": [
                "Purchase Order", "Purchase Receipt", "Purchase Invoice"]},
            {"label": _("Warehouse Request"), "items": ["Warehouse Request"]},
            {"label": _("Claim"), "items": ["Expense Claim"]}
        ],
    }


@frappe.whitelist()
def search_machine_numbers(machine_no):
    issue_doc = frappe.get_list(
        "Issue",
        filters={"machine_number": ["like", f"%{machine_no}%"]},
        fields=["name"],
    )

    project_doc = frappe.get_list(
        "Project",
        filters={"machine_numbers": ["like", f"%{machine_no}%"]},
        fields=["name"],
    )

    warehouse_request_doc = frappe.get_list(
        "Warehouse Request",
        or_filters=[
            [f"{i}_machine_number", "like", f"%{machine_no}%"] for i in range(1, 11)
        ],
        fields=["name"],
    )

    return {"issue": issue_doc, "project": project_doc, "warehouse-request": warehouse_request_doc}
