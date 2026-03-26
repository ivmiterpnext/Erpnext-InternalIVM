import json
import frappe


def get_ticket_doctype(issue_type):
    """Generate ticket doctype name from issue type"""
    return f"{issue_type} Ticket"

def create_linked_ticket_on_insert(doc):
    """Automatically create linked sub-ticket when Issue is created"""

    if doc.issue_type and not doc.sub_ticket:
        ticket_doctype = get_ticket_doctype(doc.issue_type)
        ticket_name = create_linked_ticket(doc.name, doc.issue_type)

        # Update in memory and database using dynamic link fields
        doc.set('sub_ticket_type', ticket_doctype)
        doc.set('sub_ticket', ticket_name)

        frappe.db.set_value('Issue', doc.name, {
            'sub_ticket_type': ticket_doctype,
            'sub_ticket': ticket_name
        }, update_modified=False)
        frappe.db.commit()

@frappe.whitelist()
def create_linked_ticket(issue_name, issue_type):
    """
    Create a linked sub-ticket document based on issue type

    Returns:
        str: Name of the created or existing sub-ticket
    """
    ticket_doctype = get_ticket_doctype(issue_type)
    issue = frappe.get_doc('Issue', issue_name)

    # Return existing ticket if already linked
    if issue.sub_ticket and issue.sub_ticket_type == ticket_doctype:
        return issue.sub_ticket

    # Validate that the ticket doctype exists
    if not frappe.db.exists('DocType', ticket_doctype):
        frappe.throw(f"Ticket DocType '{ticket_doctype}' does not exist")

    # Create new linked ticket (name will be set by autoname() method)
    ticket = frappe.get_doc({
        'doctype': ticket_doctype,
        'issue': issue_name
    })
    ticket.insert(ignore_permissions=True)

    # Update the Issue with both sub_ticket fields
    issue.db_set('sub_ticket_type', ticket_doctype, update_modified=False)
    issue.db_set('sub_ticket', ticket.name, update_modified=False)
    frappe.db.commit()

    frappe.logger().info(f"Created {ticket_doctype} '{ticket.name}' for Issue '{issue_name}'")

    return ticket.name

@frappe.whitelist()
def save_sub_ticket(ticket_doctype, ticket_name, field_values):
    """
    Save sub ticket field values for any ticket type

    Returns:
        dict: Updated sub-ticket document as a dictionary
    """
    if isinstance(field_values, str):
        field_values = json.loads(field_values)

    ticket = frappe.get_doc(ticket_doctype, ticket_name)

    for field, value in field_values.items():
        ticket.set(field, value)

    ticket.save(ignore_permissions=True)
    frappe.logger().info(f"Saved {ticket_doctype} '{ticket_name}' with {len(field_values)} field(s)")

    return ticket.as_dict()
