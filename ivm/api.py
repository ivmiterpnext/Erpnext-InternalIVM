import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils.data import getdate, add_days
import math
import json
import time
from frappe.utils.jinja import render_template


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
          try:
            workspace_name = workspace.get("name")

            if workspace_name in modules:
                data = frappe.get_doc("Workspace", workspace_name)
                data.is_hidden = 0  # Set is_hidden to 0 for matching modules

            else:
                data = frappe.get_doc("Workspace", workspace_name)
                data.is_hidden = 1  # Set is_hidden to 1 for non-matching modules
            data.save(ignore_permissions=True)
            frappe.db.commit()
          except Exception:
            frappe.db.rollback()
    # This part of code is for the user who is having admin role-------------------------
    else:
        workspaces = frappe.get_list("Workspace", fields=["name"])
        for workspace in workspaces:
          try:
            workspace_name = workspace.get("name")
            data = frappe.get_doc("Workspace", workspace_name)
            data.is_hidden = 0  # Set is_hidden to 1 for non-matching modules
            data.save()
            frappe.db.commit()
          except Exception:
            frappe.db.rollback()


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
            frappe.db.commit()
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

    frappe.db.commit()


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
