import frappe
import requests
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils.data import getdate, add_days
import math

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
        "fieldname": "issue",
        "non_standard_fieldnames": {"Warehouse Request": "related_case", "Issue": "parent_case"},
        "transactions": [
            {"label": _("Activity"), "items": ["Task"]},
            {"label": _("Warehouse Request"), "items": ["Warehouse Request"]},
            {"label": _("Related Cases"), "items": ["Issue"]}]}


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
    modules = ['IVM', 'CRM', 'Projects', 'Warehouse Requests',
               'Tickets', 'Receivables', 'Vending Management']
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
        email = None
        if (doc.email_account):
            email = frappe.db.get_value(
                'Email Account', {'name': doc.email_account}, "name")

        if email:
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


@frappe.whitelist()
def calculate_closed_opportunity_total(customer_name):
    # Initialize the total value
    total_value = 0
    equipment_total = 0

    month_mapping = {
        'None': 0,
        '12 Months': 12,
        '18 Months': 18,
        '24 Months': 24,
        '36 Months': 36,
        '48 Months': 48,
        '60 Months': 60,
        '72 Months': 72
    }

    # Fetch all closed opportunities for the given customer
    opportunities = frappe.get_all(
        "Opportunity",
        filters={
            "customer_name": customer_name,
            "sales_stage": "Closed Won"  # Assuming "Closed" is the status for closed opportunities
        },
        fields=["name", "number_of_machines", "per_machine_purchase_valueee", "number_of_primary_lockers",
                "custom_number_of_lockers", "per_locker_purchase_valuee",  # Corrected field name
                "per_secondary_locker_purchase_valueee",  # Corrected field name
                # Corrected field name
                "per_machine_monthly_lease_feeee", "per_locker_monthly_lease_feeee",
                "number_of_secondary_lockers", "per_secondary_locker_monthly_lease_feeee", "sv_term", 'equipment_total']
    )

    # Loop through each closed opportunity and calculate the total
    for opportunity in opportunities:
        opportunity.custom_number_of_lockers = opportunity.number_of_primary_lockers + \
            opportunity.number_of_secondary_lockers
        sv_term_numeric = month_mapping.get(opportunity.sv_term, 0)

        total_value += (
            opportunity.number_of_machines * opportunity.per_machine_purchase_valueee +
            opportunity.custom_number_of_lockers * opportunity.per_locker_purchase_valuee +
            opportunity.number_of_secondary_lockers * opportunity.per_secondary_locker_purchase_valueee +
            (opportunity.per_machine_monthly_lease_feeee * opportunity.number_of_machines) * sv_term_numeric +
            (opportunity.custom_number_of_lockers * opportunity.per_locker_monthly_lease_feeee) * sv_term_numeric +
            (opportunity.number_of_secondary_lockers *
             opportunity.per_secondary_locker_monthly_lease_feeee) * sv_term_numeric
        )
    return total_value


@frappe.whitelist()
def deployment_location_equipments(opportunity, machines, lockers):
    doc = frappe.get_doc("Opportunity", opportunity)
    doc.custom_total_machines_from_dls = machines
    doc.custom_total_lockers_from_dls = lockers
    machines = int(machines)
    lockers = int(lockers)
    doc.equipment_total = machines+lockers

    doc.save(ignore_permissions=True)


@frappe.whitelist()
def create_warehouse_request(doc):
    # Check if a warehouse request already exists for the project_name
    existing_request = frappe.get_all("Warehouse Request", filters={
                                      "related_project": doc.name})
    if not existing_request:
        # Create a new dictionary for warehouse_request
        warehouse = {}
        fields_to_copy = ['vat', 'subject', 'description', 'internal_notes', 'locker_configuration_details', 'additional_locker_information', 'vault_power_configuration_details',
                          'rfid_1_settings', 'rfid_2_settings', 'card_reader_type', 'shipping_company', 'kiosk_options', 'kvm_switch_options', 'monitor_options', 'network_options',
                          'electrical_outlet_in_bins', 'network_port_in_bins', 'interior_kiosk_lighting', 'locker_bin_door_type', 'countertop_color', 'ada_side_table',
                          'kiosk_side_for_table', 'monitor_mount']

        # Loop through the fields and copy them from doc to warehouse_request
        for field in fields_to_copy:
            warehouse[field] = doc.get(field)

        warehouse_request = frappe.new_doc("Warehouse Request")
        for field, value in warehouse.items():
            setattr(warehouse_request, field, value)
        warehouse_request.related_project = doc.name
        warehouse_request.machine_names = doc.machine_numbers
        warehouse_request.connectivity = doc.connectivity_type
        warehouse_request.carrier = doc.cell_carrier
        warehouse_request.contact = doc.contact_name
        warehouse_request.tracking_number = doc.shipping_tracking_number
        warehouse_request.owner_name = doc.users[0].user
        warehouse_request.account = doc.customer
        warehouse_request.created_by = frappe.session.user
        warehouse_request.created_date = frappe.utils.nowdate()
        warehouse_request.insert(ignore_permissions=True)
        warehouse_request.save(ignore_permissions=True)
        frappe.db.commit()


@frappe.whitelist()
def deployment_to_warehouse(doc, method):
    if all([doc.planogram_approved_date, doc.graphic_design_approved_date, doc.kiosk_configuration_approved_date, doc.locker_configuration_approved_date, doc.vault_configuration_approved_date]):
        create_warehouse_request(doc)


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
def fetching_dates(doc, method):
    doc.db_set('created_date', doc.creation)
    doc.db_set('custom_modified_date', doc.modified)
    doc.db_set('custom_created_by', doc.owner)
    doc.db_set('custom_modified_by', doc.modified_by)
    doc.reload()


@frappe.whitelist()
def search_machine_numbers(machine_no):
    issue_doc = frappe.db.sql(
        """SELECT name FROM `tabIssue` WHERE machine_number LIKE %s""",
        (f"%{machine_no}%",),
        as_dict=True
    )

    project_doc = frappe.db.sql(
        """SELECT name FROM `tabProject` WHERE machine_numbers LIKE %s""",
        (f"%{machine_no}%",),
        as_dict=True
    )

    warehouse_request_doc = frappe.db.sql(
        """
        SELECT name
        FROM `tabWarehouse Request`
        WHERE
            1_machine_number LIKE %s
            OR 2_machine_number LIKE %s
            OR 3_machine_number LIKE %s
            OR 4_machine_number LIKE %s
            OR 5_machine_number LIKE %s
            OR 6_machine_number LIKE %s
            OR 7_machine_number LIKE %s
            OR 8_machine_number LIKE %s
            OR 9_machine_number LIKE %s
            OR 10_machine_number LIKE %s
        """,
        tuple([f"%{machine_no}%"] * 10),
        as_dict=True
    )

    return {"issue": issue_doc, "project": project_doc, "warehouse-request": warehouse_request_doc}
