import frappe
import requests
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils.data import getdate, add_days
import math
import json
import time
import re
import pyodbc
from frappe.utils.jinja import render_template

# function to get user id from salesloft


def get_user_id(lead_owener):
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token

    if lead_owener:
        url = "https://api.salesloft.com/v2/users"
        payload = {}
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        response = response.json()
        data = response["data"]
        for i in data:
            if i['email'].strip() == lead_owener.strip():
                user_id = i["id"]
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
def create_salesloft_person(email, first_name='', last_name='', job_title='', city='', state='', country='', company='', website='', phone='', phone_ext='', mobile_no='', lead_owner=""):

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

    if lead_owner and lead_owner != "Administrator":
        user_id = get_user_id(lead_owner)
        if user_id:
            payload["owner_id"] = user_id
            response = make_salesloft_api_call(
                url, method="POST", payload=payload)

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
def get_contact_name(doctype, txt, searchfield, start, page_len, filters):
    names = filters.get('name')
    if names == "":
        return []
    list_of_records = frappe.db.sql("""SELECT DISTINCT c.name
        FROM `tabContact` c
        INNER JOIN `tabDynamic Link` dl ON c.name = dl.parent
        WHERE dl.link_doctype = 'Customer' AND dl.link_title = '{0}' """.format(names))

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
            try:
                data.save(ignore_permissions=True)
            except frappe.LinkValidationError:
                # Skip workspaces with broken links
                frappe.db.rollback()
                pass
    # This part of code is for the user who is having admin role-------------------------
    else:
        workspaces = frappe.get_list("Workspace", fields=["name"])
        for workspace in workspaces:
            workspace_name = workspace.get("name")
            data = frappe.get_doc("Workspace", workspace_name)
            data.is_hidden = 0  # Set is_hidden to 1 for non-matching modules
            try:
                data.save()
            except frappe.LinkValidationError:
                # Skip workspaces with broken links
                frappe.db.rollback()
                pass


@frappe.whitelist()
def creating_issue(doc, method):
    try:
        attachments = doc.get_attachments()
        reference_name = frappe.get_all('Communication', filters={'reference_name': doc.reference_name}, fields=['reference_name'])
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
            if (issue_type in ['IT', 'Support', 'Receivable', 'Reconfiguration', 'Vending Management']):
                customer = fetch_customer_name_and_contact(doc.sender)
                issue_name.customer = customer.get('customer_name')
                issue_name.contact_name = customer.get('contact_name')
            issue_name.issue_type = issue_type
            if (len(reference_name) <= 1):
                issue_name.description = doc.content
            issue_name.save()
            if (attachments):
                frappe.log_error("attachments", attachments)
                file_urls = [url['file_url'] for url in attachments]
                for links in file_urls:
                    file = frappe.get_doc({
                        'doctype': 'File',
                        'is_private': 1,
                        'file_url': links,
                        'attached_to_doctype': 'Issue',
                        'attached_to_name': doc.reference_name
                    })
                    file.save()
    except Exception as e:
        pass


def fetch_customer_name_and_contact(sender_name):
    try:
        contact_name = frappe.db.sql("""SELECT DISTINCT c.name AS contact_name, dl.link_name AS customer_name
                                   FROM `tabContact` c
                                   INNER JOIN `tabContact Email` ce ON c.name = ce.parent
                                   LEFT JOIN `tabDynamic Link` dl ON c.name = dl.parent AND dl.link_doctype = 'Customer'
                                   WHERE ce.email_id = '{0}' """.format(sender_name), as_dict=True)
        return contact_name[0]
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
def create_warehouse_request(doc, reason, attached_files=None):
    # Check if doc is a dictionary
    doc = json.loads(doc)
    if isinstance(doc, dict):
        # Check if a warehouse request already exists for the project_name
        if 'name' in doc:
            existing_request = frappe.get_all("Warehouse Request", filters={
                "related_project": doc['name'], "request_reason": reason})
            if not existing_request:
                # Create a new dictionary for warehouse_request
                warehouse = {}
                fields_to_copy = ['vat', 'subject', 'description', 'internal_notes', 'locker_configuration_details', 'additional_locker_information', 'vault_power_configuration_details',
                                  'rfid_1_settings', 'rfid_2_settings', 'card_reader_type', 'shipping_company', 'kiosk_options', 'kvm_switch_options', "monitor_options", 'network_options',
                                  'electrical_outlet_in_bins', 'network_port_in_bins', 'interior_kiosk_lighting', 'locker_bin_door_type', 'countertop_color', 'ada_side_table',
                                  'kiosk_side_for_table', 'monitor_mount']

                # Loop through the fields and copy them from doc to warehouse_request
                for field in fields_to_copy:
                    warehouse[field] = doc.get(field)

                warehouse_request = frappe.new_doc("Warehouse Request")
                for field, value in warehouse.items():
                    setattr(warehouse_request, field, value)
                warehouse_request.machine_key = doc.get('machine_key')
                warehouse_request.locale = doc.get('locale')
                warehouse_request.machine_ownership_status = doc.get(
                    'machine_ownership_status')
                warehouse_request.request_reason = reason
                warehouse_request.related_project = doc.get('name')
                warehouse_request.machine_names = doc.get('machine_numbers')
                warehouse_request.connectivity = doc.get('connectivity_type')
                warehouse_request.carrier = doc.get('cell_carrier')
                warehouse_request.contact = doc.get('contact_name')
                warehouse_request.tracking_number = doc.get(
                    'shipping_tracking_number')
                warehouse_request.shipping_address = doc.get(
                    'address')

                # Check if users and user are available in doc
                if doc.get('users') and doc['users'][0].get('user'):
                    warehouse_request.owner_name = doc['users'][0]['user']
                else:
                    warehouse_request.owner_name = None

                warehouse_request.account = doc.get('customer')
                warehouse_request.created_by = frappe.session.user
                warehouse_request.created_date = frappe.utils.nowdate()
                warehouse_request.insert(ignore_permissions=True)
                warehouse_request.save(ignore_permissions=True)

                # Sleep for 2 seconds
                time.sleep(2)

                # Attach files only if attached_files is not None and not an empty string
                warehouse_request.warehouse_request_name = warehouse_request.name
                if attached_files:
                    doc = frappe.get_doc({'doctype': 'File',
                                          'is_private': 1,
                                          'file_url': attached_files,
                                          'attached_to_doctype': 'Warehouse Request',
                                          'attached_to_name': warehouse_request.name
                                          })
                    doc.save()
                return reason

            else:
                pass


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


def send_auto_reply(self, communication, email):
    frappe.log_error('email.from_email',email.from_email)
    """Send auto reply if set."""
    from frappe.core.doctype.communication.email import set_incoming_outgoing_accounts

    if self.enable_auto_reply:

        set_incoming_outgoing_accounts(communication)

        unsubscribe_message = (self.send_unsubscribe_message and _(
            "Leave this conversation")) or ""
        issue_name = frappe.get_all('Communication', filters={
                                    'reference_name': communication.reference_name}, fields=['reference_name'])
        if (len(issue_name) <= 1):
            frappe.sendmail(
                recipients=[email.from_email],
                sender=self.email_id,
                reply_to=communication.incoming_email_account,
                subject=" ".join([_("Re:"), communication.subject]),
                content=render_template(
                    self.auto_reply_message or "", communication.as_dict())
                or frappe.get_template("templates/emails/auto_reply.html").render(communication.as_dict()),
                reference_doctype=communication.reference_doctype,
                reference_name=communication.reference_name,
                # send back the Message-Id as In-Reply-To
                in_reply_to=email.mail.get(
                    "Message-Id"),
                unsubscribe_message=unsubscribe_message,
            )
@frappe.whitelist()
def fetch_contacts_from_apollo(page,searchKeyword):   
   url = "https://api.apollo.io/v1/contacts/search"


   data = {
       "api_key": frappe.get_single('Apollo  Integration Settings').api_key,
       "page": page,
   }
   if searchKeyword:
       data = {
       "api_key": frappe.get_single('Apollo  Integration Settings').api_key,
       "q_keywords": searchKeyword,
   }




   headers = {
       'Cache-Control': 'no-cache',
       'Content-Type': 'application/json'
   }


   response = requests.request("POST", url, headers=headers, json=data)
  
   if response.status_code == 200:
       apollo_data = response.json()
      
      
       for contact in apollo_data.get("contacts", []):
           contact['disabled'] = frappe.db.exists({"doctype": "Lead", "email_id":contact.get('email')})




       return apollo_data
   else:
       return {
           'error': 'Failed to fetch data from Apollo.io'
       }


@frappe.whitelist()
def createLeads(selectedContacts):
   contacts_data = json.loads(selectedContacts)


   for contact in contacts_data:
       lead = frappe.new_doc("Lead")
       lead.first_name = contact.get("first_name")
       lead.last_name = contact.get("last_name")
       lead.email_id = contact.get("email")
       lead.mobile_no = contact.get("sanitized_phone")
       lead.title = contact.get("title")
       lead.city = contact.get("city")
       lead.state = contact.get("state")
       lead.country = contact.get("country")
       lead.website = contact.get("website_url")
       lead.insert()
       lead.save()
      
       salesloft_user = check_salesloft_user(contact.get("email"))
      
       if not salesloft_user:
           create_salesloft_person(email=contact.get("email"), first_name=contact.get("first_name"), last_name= contact.get("last_name"), job_title=contact.get("title"), city= contact.get("city"), state=contact.get("state"), country=contact.get("country"), company='', website=contact.get("website_url"), phone='', phone_ext='', mobile_no=contact.get("sanitized_phone"), lead_owner=frappe.session.user)


# ============================================================================
# Contact Matching & Audit Functions (MSSQL <-> Frappe)
# ============================================================================

def _norm_email(v: str | None) -> str | None:
    """Normalize email address for matching."""
    if not v:
        return None
    v = v.strip().lower()
    return v or None

def _norm_phone(v: str | None) -> str | None:
    """Normalize phone number to digits only for matching."""
    if not v:
        return None
    digits = re.sub(r"\D+", "", v)
    return digits or None

def _get_conn():
    """Get MSSQL connection using site config."""
    if pyodbc is None:
        frappe.throw("pyodbc is not installed. Run: ./env/bin/pip install pyodbc")
    
    cfg = frappe.get_site_config()
    host = cfg.get("mssql_host")
    db = cfg.get("mssql_db")
    user = cfg.get("mssql_user")
    pw = cfg.get("mssql_password")
    encrypt = "yes" if int(cfg.get("mssql_encrypt", 1)) else "no"
    trust = "yes" if int(cfg.get("mssql_trust_cert", 0)) else "no"

    if not all([host, db, user, pw]):
        raise frappe.ValidationError("Missing MSSQL config in site_config.json")

    conn_str = (
        "Driver={ODBC Driver 17 for SQL Server};"
        f"Server={host};"
        f"Database={db};"
        f"UID={user};PWD={pw};"
        f"Encrypt={encrypt};TrustServerCertificate={trust};"
        "Connection Timeout=30;"
    )
    return pyodbc.connect(conn_str)



@frappe.whitelist()
def run_contact_audit(limit: int = 0):
    """
    One-time audit: compare MSSQL canonical contacts vs Frappe Contact
    and produce a report (returns counts + sample rows).
    """
    limit = int(limit or 0)

    # 1) Pull MSSQL canonical rows (from your view)
    with _get_conn() as conn:
        cur = conn.cursor()
        sql = """
        SELECT
            SourceRID,
            CanonicalRID,
            EmailAddress,
            Phone1,
            FirstName,
            LastName
        FROM dbo.vw_PTL_CanonicalContact
        """
        if limit > 0:
            sql = f"SELECT TOP ({limit}) " + sql.split("SELECT", 1)[1]
        cur.execute(sql)
        mssql_rows = cur.fetchall()

    # Index MSSQL by matching keys
    by_email = {}
    by_phone = {}
    by_name_phone = {}

    for r in mssql_rows:
        email = _norm_email(getattr(r, "EmailAddress", None))
        phone = _norm_phone(getattr(r, "Phone1", None))
        first = (getattr(r, "FirstName", None) or "").strip().lower()
        last = (getattr(r, "LastName", None) or "").strip().lower()

        if email:
            by_email[email] = r
        if phone:
            by_phone[phone] = r
        if first and last and phone:
            by_name_phone[(first, last, phone)] = r

    # 2) Pull Frappe Contacts
    contacts = frappe.get_all(
        "Contact",
        fields=["name", "email_id", "phone", "mobile_no", "first_name", "last_name", "custom_css_contact_id"],
        limit_page_length=0,
    )

    matched = []
    unmatched_frappe = []
    unmatched_mssql = set([getattr(r, "CanonicalRID", None) for r in mssql_rows])

    for c in contacts:
        email = _norm_email(c.get("email_id"))
        phones = list(filter(None, [_norm_phone(c.get("phone")), _norm_phone(c.get("mobile_no"))]))
        first = (c.get("first_name") or "").strip().lower()
        last = (c.get("last_name") or "").strip().lower()

        hit = None
        reason = None

        if email and email in by_email:
            hit = by_email[email]
            reason = "email"
        elif phones:
            for p in phones:
                if p in by_phone:
                    hit = by_phone[p]
                    reason = "phone"
                    break
        if not hit and first and last and phones:
            key = (first, last, phones[0])
            if key in by_name_phone:
                hit = by_name_phone[key]
                reason = "name+phone"

        if hit:
            canon = getattr(hit, "CanonicalRID", None)
            if canon in unmatched_mssql:
                unmatched_mssql.remove(canon)
            matched.append({
                "contact": c["name"],
                "match_on": reason,
                "canonical_rid": canon,
                "existing_css_contact_id": c.get("custom_css_contact_id"),
            })
        else:
            unmatched_frappe.append({"contact": c["name"]})

    return {
        "mssql_rows": len(mssql_rows),
        "frappe_contacts": len(contacts),
        "matched": len(matched),
        "unmatched_frappe": len(unmatched_frappe),
        "unmatched_mssql": len(unmatched_mssql),
        "matched_sample": matched[:50],
        "unmatched_frappe_sample": unmatched_frappe[:50],
        "unmatched_mssql_sample": list(unmatched_mssql)[:50],
    }


@frappe.whitelist()
def apply_contact_matches(dry_run: int = 1):
    """
    Apply the matched contacts by updating custom_css_contact_id in Frappe.
    
    Args:
        dry_run: 1 = just report what would be updated, 0 = actually update
    """
    dry_run = int(dry_run or 1)
    
    # Re-run audit to get matches
    audit = run_contact_audit(limit=0)
    matched = audit.get("matched_sample", [])
    
    # Get all matches, not just sample
    if audit["matched"] > 50:
        # Run full audit without limit
        limit = 0
        with _get_conn() as conn:
            cur = conn.cursor()
            sql = """
            SELECT
                SourceRID,
                CanonicalRID,
                EmailAddress,
                Phone1,
                FirstName,
                LastName
            FROM dbo.vw_PTL_CanonicalContact
            """
            cur.execute(sql)
            columns = [column[0] for column in cur.description]
            mssql_rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        by_email = {}
        by_phone = {}
        by_name_phone = {}

        for r in mssql_rows:
            email = _norm_email(r.get("EmailAddress"))
            phone = _norm_phone(r.get("Phone1"))
            first = (r.get("FirstName") or "").strip().lower()
            last = (r.get("LastName") or "").strip().lower()

            if email:
                by_email[email] = r
            if phone:
                by_phone[phone] = r
            if first and last and phone:
                by_name_phone[(first, last, phone)] = r

        contacts = frappe.get_all(
            "Contact",
            fields=["name", "email_id", "phone", "mobile_no", "first_name", "last_name", "custom_css_contact_id"],
            limit_page_length=0,
        )

        matched = []
        for c in contacts:
            email = _norm_email(c.get("email_id"))
            phones = list(filter(None, [_norm_phone(c.get("phone")), _norm_phone(c.get("mobile_no"))]))
            first = (c.get("first_name") or "").strip().lower()
            last = (c.get("last_name") or "").strip().lower()

            hit = None
            reason = None

            if email and email in by_email:
                hit = by_email[email]
                reason = "email"
            elif phones:
                for p in phones:
                    if p in by_phone:
                        hit = by_phone[p]
                        reason = "phone"
                        break
            if not hit and first and last and phones:
                key = (first, last, phones[0])
                if key in by_name_phone:
                    hit = by_name_phone[key]
                    reason = "name+phone"

            if hit:
                matched.append({
                    "contact": c["name"],
                    "match_on": reason,
                    "canonical_rid": hit.get("CanonicalRID"),
                    "existing_css_contact_id": c.get("custom_css_contact_id"),
                })

    updated = 0
    skipped = 0
    errors = []

    for match in matched:
        contact_name = match["contact"]
        canonical_rid = match["canonical_rid"]
        existing_id = match["existing_css_contact_id"]
        
        # Skip if already has the ID
        if existing_id == canonical_rid:
            skipped += 1
            continue
            
        if dry_run:
            frappe.logger().info(f"[DRY RUN] Would update {contact_name} with CanonicalRID={canonical_rid}")
        else:
            try:
                doc = frappe.get_doc("Contact", contact_name)
                doc.custom_css_contact_id = canonical_rid
                doc.save(ignore_permissions=True)
                updated += 1
            except Exception as e:
                errors.append({"contact": contact_name, "error": str(e)})

    return {
        "dry_run": bool(dry_run),
        "total_matches": len(matched),
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "message": "Dry run complete - no changes made" if dry_run else f"Updated {updated} contacts"
    }

@frappe.whitelist()
def import_mssql_to_frappe(dry_run: int = 1, limit: int = 0):
    """
    Import unmatched MSSQL contacts into Frappe.
    
    Args:
        dry_run: 1 = just report what would be created, 0 = actually create
        limit: Limit number of contacts to import (0 = all)
    """
    dry_run = int(dry_run or 1)
    limit = int(limit or 0)
    
    # Get all MSSQL contacts
    with _get_conn() as conn:
        cur = conn.cursor()
        sql = """
        SELECT
            SourceRID,
            CanonicalRID,
            EmailAddress,
            Phone1,
            FirstName,
            LastName
        FROM dbo.vw_PTL_CanonicalContact
        """
        cur.execute(sql)
        columns = [column[0] for column in cur.description]
        mssql_rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    # Get existing Frappe contacts with CSS ID
    existing_css_ids = set()
    contacts_with_id = frappe.get_all(
        "Contact",
        filters={"custom_css_contact_id": ["is", "set"]},
        fields=["custom_css_contact_id"],
    )
    for c in contacts_with_id:
        if c.get("custom_css_contact_id"):
            existing_css_ids.add(c["custom_css_contact_id"])

    # Build matching indexes
    contacts = frappe.get_all(
        "Contact",
        fields=["name", "email_id", "phone", "mobile_no", "first_name", "last_name"],
        limit_page_length=0,
    )
    
    frappe_emails = {_norm_email(c.get("email_id")) for c in contacts if c.get("email_id")}
    frappe_phones = set()
    for c in contacts:
        for phone in [c.get("phone"), c.get("mobile_no")]:
            normalized = _norm_phone(phone)
            if normalized:
                frappe_phones.add(normalized)

    # Find unmatched MSSQL contacts
    to_import = []
    for r in mssql_rows:
        canonical_rid = r.get("CanonicalRID")
        
        # Skip if already linked
        if canonical_rid in existing_css_ids:
            continue
            
        # Skip if email or phone already exists (potential match)
        email = _norm_email(r.get("EmailAddress"))
        phone = _norm_phone(r.get("Phone1"))
        
        if email and email in frappe_emails:
            continue
        if phone and phone in frappe_phones:
            continue
            
        to_import.append(r)

    # Apply limit
    if limit > 0:
        to_import = to_import[:limit]

    created = 0
    errors = []
    
    for r in to_import:
        if dry_run:
            frappe.logger().info(f"[DRY RUN] Would create Contact: {r.get('FirstName')} {r.get('LastName')} (CanonicalRID={r.get('CanonicalRID')})")
            created += 1
        else:
            try:
                doc = frappe.new_doc("Contact")
                doc.first_name = r.get("FirstName") or "Unknown"
                doc.last_name = r.get("LastName") or ""
                doc.email_id = r.get("EmailAddress")
                doc.phone = r.get("Phone1")
                doc.custom_css_contact_id = r.get("CanonicalRID")
                doc.insert(ignore_permissions=True)
                created += 1
            except Exception as e:
                errors.append({"mssql_rid": r.get("CanonicalRID"), "error": str(e)})

    return {
        "dry_run": bool(dry_run),
        "total_unmatched": len(to_import) if limit == 0 else f"{len(to_import)} (limited)",
        "created": created,
        "errors": errors,
        "message": "Dry run complete - no changes made" if dry_run else f"Created {created} contacts"
    }

@frappe.whitelist()
def import_frappe_to_mssql(dry_run: int = 1, limit: int = 0):
    """
    Import unmatched Frappe contacts into MSSQL.
    
    Args:
        dry_run: 1 = just report what would be created, 0 = actually create
        limit: Limit number of contacts to import (0 = all)
    """
    dry_run = int(dry_run or 1)
    limit = int(limit or 0)
    
    # Get Frappe contacts without CSS ID
    filters = [["custom_css_contact_id", "is", "not set"]]
    contacts = frappe.get_all(
        "Contact",
        filters=filters,
        fields=["name", "email_id", "phone", "mobile_no", "first_name", "last_name"],
        limit_page_length=limit if limit > 0 else 0,
    )

    created = 0
    errors = []
    
    for c in contacts:
        if dry_run:
            frappe.logger().info(f"[DRY RUN] Would create MSSQL contact: {c.get('first_name')} {c.get('last_name')}")
            created += 1
        else:
            try:
                with _get_conn() as conn:
                    cur = conn.cursor()
                    # Insert into MSSQL Contact table - will auto-appear in canonical view
                    sql = """
                    INSERT INTO dbo.tbl_PTL_Contact (EmailAddress, Phone1, FirstName, LastName)
                    OUTPUT INSERTED.RID
                    VALUES (?, ?, ?, ?)
                    """
                    cur.execute(sql, (
                        c.get("email_id"),
                        c.get("phone") or c.get("mobile_no"),
                        c.get("first_name"),
                        c.get("last_name")
                    ))
                    
                    # Get the new CanonicalRID
                    row = cur.fetchone()
                    new_canonical_rid = row[0] if row else None
                    
                    conn.commit()
                    
                    # Update Frappe with the new ID
                    if new_canonical_rid:
                        doc = frappe.get_doc("Contact", c["name"])
                        doc.custom_css_contact_id = new_canonical_rid
                        doc.save(ignore_permissions=True)
                        created += 1
                        
            except Exception as e:
                errors.append({"contact": c["name"], "error": str(e)})

    return {
        "dry_run": bool(dry_run),
        "total_unmatched": len(contacts),
        "created": created,
        "errors": errors,
        "message": "Dry run complete - no changes made" if dry_run else f"Created {created} contacts in MSSQL"
    }
