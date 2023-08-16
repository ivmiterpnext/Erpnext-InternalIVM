import frappe
import requests
from frappe.model.mapper import get_mapped_doc
from frappe import _

# Function to get the SalesLoft API token from the "SalesLoft Settings" doctype


def get_salesloft_api_token():
    api_token = frappe.get_value(
        "SalesLoft Settings", None, "salesloft_api_token")

    if not api_token:
        frappe.throw("SalesLoft API Token not set in SalesLoft Settings")

    return api_token

# Function to make API calls to SalesLoft


def make_salesloft_api_call(url, method="GET", payload=None):
    SALESLOFT_API_TOKEN = get_salesloft_api_token()

    if not SALESLOFT_API_TOKEN:
        frappe.throw("SalesLoft API Token not set in SalesLoft Settings")

    headers = {"Authorization": f"Bearer {SALESLOFT_API_TOKEN}"}
    response = requests.request(method, url, json=payload, headers=headers)

    return response

# Function to check if the SalesLoft user already exists


@frappe.whitelist(allow_guest=True)
def check_salesloft_user(email):
    url = "https://api.salesloft.com/v2/people"
    response = make_salesloft_api_call(url)

    for person in response.json().get("data", []):
        if person.get("email_address") == email:
            return person

    return None

# Function to create a new SalesLoft person


@frappe.whitelist(allow_guest=True)
def create_salesloft_person(email, first_name='', last_name='', job_title='', city='', state='', country='', company='', website='', phone='', phone_ext='', mobile_no=''):

    url = "https://api.salesloft.com/v2/people"
    payload = {
        "email_address": email,
        "first_name": first_name,
        'last_name': last_name,
        'title': job_title,
        'city': city,
        'state': state,
        'country': country,
        'person_company_name': company,
        'person_company_website': website,
        'phone': phone,
        'phone_extension': phone_ext,
        'mobile_phone': mobile_no
    }
    print(payload)
    response = make_salesloft_api_call(url, method="POST", payload=payload)

    if response.status_code == 201:
        created_person = response.json()
        return created_person["data"]["id"]
    else:
        return None


@frappe.whitelist()
def get_child_tasks(parent_task):
    if (parent_task != ""):
        return [frappe.db.get_list('Task', filters={'parent_task': parent_task}, fields=['name', 'subject'])]


@frappe.whitelist()
def create_case(source_name, target_doc=None):
    def set_missing_values(source, target):
        target.opportunity_name = source.name
        if source.opportunity_from == "Lead":
            target.lead_name = source.party_name

        doclist = get_mapped_doc(
            "Opportunity",
            source_name,
            {
                "Opportunity": {
                    "doctype": "Project",
                    "field_map": {"currency": "default_currency", "customer_name": "customer_name"},
                }
            },
            target_doc,
            set_missing_values,
        )

        return doclist


def get_data(data):
    return {
        "heatmap": True,
        "heatmap_message": _("This is based on the Time Sheets created against this project"),
        "fieldname": "project",
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
            {"label": ("Events"), "items": ["Event"]},
        ],
    }


@frappe.whitelist()
def getCheckboxStatus():
    return frappe.get_doc("SalesLoft Settings").enable_salesloft_integration


@frappe.whitelist()
def arrangeing_records(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql(""" select stage_name from `tabSales Stage` ORDER BY  creation ASC""")

@frappe.whitelist()
def set_cell_Carrier(option):
    doc = frappe.get_doc("Connectivity Type", option)
    return doc.cell_carrier

@frappe.whitelist()
def get_issue_type_record(record_name):
    doc = frappe.get_doc("Issue Type", record_name)
    return doc.as_dict()
@frappe.whitelist()
def get_connectivity_type_record(record_name):
    doc = frappe.get_doc("Connectivity Type", record_name)
    return doc.as_dict()

#ram
@frappe.whitelist(allow_guest=True)
def get_case_sub_reason_options(case_reason="VM Support"):
    doc = frappe.get_doc("Case Reason",case_reason)
    child_table_records = doc.get("case_sub_reason")
    child_field_values = [child_record.get("case_sub_reason") for child_record in child_table_records]
    return child_field_values