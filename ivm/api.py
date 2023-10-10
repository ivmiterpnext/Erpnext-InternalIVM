import frappe
import requests
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils.data import getdate, add_days
import math

# function to get user id from salesloft
def get_user_id(lead_owener):
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token
    
    if lead_owener:
        url = "https://api.salesloft.com/v2/users"
        payload={}
        headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        response = response.json()
        data = response["data"]
        for i in data:
            if i['email'].strip()==lead_owener.strip():
                user_id =  i["id"]
                return user_id
        return False


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
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    guid = salesloft_doc.guid

    payload = {"email_addresses": [email]}
    response = make_salesloft_api_call(url, payload=payload)

    for person in response.json().get("data", []):
        if person.get("email_address") == email:
            return person

    return None

# Function to create a new SalesLoft person


@frappe.whitelist(allow_guest=True)
def create_salesloft_person(email, first_name='', last_name='', job_title='', city='', state='', country='', company='', website='', phone='', phone_ext='', mobile_no='',lead_owner=""):

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
    
    if lead_owner and lead_owner !="Administrator":
        user_id = get_user_id(lead_owner)
        if user_id:
            payload["owner_id"] = user_id
            response = make_salesloft_api_call(url, method="POST", payload=payload)

            if response.status_code == 201:
                created_person = response.json()
                return created_person["data"]["id"]
            else:
                return None
        return "noUserFound"
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


@frappe.whitelist(allow_guest=True)
def get_case_sub_reason_options(case_reason):
    if case_reason == "":
        return []
    doc = frappe.get_doc("Case Reason", case_reason)
    child_table_records = doc.get("case_sub_reason")
    child_field_values = [child_record.get(
        "case_sub_reason") for child_record in child_table_records]
    return child_field_values


@frappe.whitelist(allow_guest=True)
def get_contact_name(name):
    if name == "":
        return []

    docs = frappe.db.get_list("Contact", pluck="name")
    list_of_records = []
    for i in docs:
        doc = frappe.get_doc("Contact", i)
        doc = doc.as_dict()
        child_records = doc.links
        if len(child_records) > 0:
            for j in range(len(child_records)):
                if child_records[j]['link_doctype'] == "Customer" and child_records[j]["link_title"] == name:
                    list_of_records.append(i)
    return list_of_records


@frappe.whitelist()
def make_project(source_name, target_doc=None):
    customer_name = frappe.db.get_value(
        'Opportunity', source_name, 'customer_name')
    customer_exists = frappe.db.exists("Customer", customer_name, cache=True)

    def set_missing_values(source, target):
        target.opportunity_name = source.name
    field_mappings = {
        "deployment_address": "associated_deployment_location",
        "sv_term": "opportunity_term",
    }
    if customer_exists:
        field_mappings["customer_name"] = "customer"
    doclist = get_mapped_doc(
        "Opportunity",
        source_name,
        {
            "Opportunity": {
                "doctype": "Project",
                "field_map": field_mappings
            }
        },
        target_doc,
        set_missing_values
    )
    return doclist


@frappe.whitelist()
def on_session_creation():
    modules = ['IVM', 'CRM', 'Projects','Warehouse Requests', 'Tickets', 'Receivables', 'Vending Management']
    # This part of code is for the user who is not having admin role----------------------------
    if 'Admin' not in frappe.get_roles(frappe.session.user):
        workspaces = frappe.get_list(
            "Workspace", fields=["name"], ignore_permissions=True)
        for workspace in workspaces:
            workspace_name = workspace.get("name")

            if workspace_name in modules:
                data = frappe.get_doc("Workspace", workspace_name)
                data.is_hidden = 0  # Set is_hidden to 0 for matching modules

            else:
                data = frappe.get_doc("Workspace", workspace_name)
                data.is_hidden = 1  # Set is_hidden to 1 for non-matching modules
            data.save(ignore_permissions=True)
            frappe.db.commit()
    # This part of code is for the user who is having admin role-------------------------
    else:
        workspaces = frappe.get_list("Workspace", fields=["name"])
        for workspace in workspaces:
            workspace_name = workspace.get("name")
            data = frappe.get_doc("Workspace", workspace_name)
            data.is_hidden = 0  # Set is_hidden to 1 for non-matching modules
            data.save()
            frappe.db.commit()


@frappe.whitelist()
def creating_issue(doc, method):
    try:
        message = doc.content
        # getting record matching to email received
        email = frappe.db.get_value('Email Account', {'email_id': doc.recipients})
        if  email:
            email_Account = frappe.get_doc("Email Account", email)
            # getting issue type from email account doctype
            issue_type = email_Account.imap_folder[0].custom_issue_type
            issue = frappe.db.get_value('Issue', {'name': doc.reference_name})
            issue_name = frappe.get_doc("Issue", issue)
            issue_name.issue_type = issue_type
            issue_name.description = message
            issue_name.save()
            frappe.db.commit()
    except Exception as e:
        pass
