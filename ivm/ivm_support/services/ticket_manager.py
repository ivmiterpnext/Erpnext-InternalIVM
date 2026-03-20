import frappe

# Map issue type to ticket doctype
TICKET_DOCTYPES = {
    'Support': 'Support Ticket',
    'Bug': 'Bug Report',
    'Sales': 'Sales Inquiry'
}


def create_linked_ticket_on_insert(doc):
    """Auto-create linked ticket when Issue is created"""

    if doc.issue_type and doc.issue_type in TICKET_DOCTYPES:
        if not doc.sub_ticket:
            ticket_name = create_linked_ticket(doc.name, doc.issue_type)
            ticket_doctype = TICKET_DOCTYPES[doc.issue_type]

            # Update in memory AND database using dynamic link fields
            doc.set('sub_ticket_type', ticket_doctype)
            doc.set('sub_ticket', ticket_name)

            frappe.db.set_value('Issue', doc.name, {
                'sub_ticket_type': ticket_doctype,
                'sub_ticket': ticket_name
            }, update_modified=False)
            frappe.db.commit()


@frappe.whitelist()
def create_linked_ticket(issue_name, issue_type):
    """Create a linked ticket document based on issue type

    Args:
        issue_name: Name of the Issue document
        issue_type: Type of ticket to create (Support, Bug, Sales)

    Returns:
        str: Name of the created or existing ticket
    """
    ticket_doctype = TICKET_DOCTYPES.get(issue_type)
    if not ticket_doctype:
        frappe.throw(f"Invalid issue type: {issue_type}")

    issue = frappe.get_doc('Issue', issue_name)

    # Return existing ticket if already linked
    if issue.sub_ticket and issue.sub_ticket_type == ticket_doctype:
        return issue.sub_ticket

    # Update the issue's sub_ticket_type field
    issue.sub_ticket_type = ticket_doctype

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

    frappe.logger().info(f"Created {ticket_doctype} {ticket.name} for Issue {issue_name}")

    return ticket.name


@frappe.whitelist()
def save_sub_ticket(ticket_doctype, ticket_name, field_values):
    """Save sub ticket field values for any ticket type

    Args:
        ticket_doctype: The ticket doctype (Support Ticket, Bug Report, Sales Inquiry)
        ticket_name: Name of the ticket document
        field_values: Dict of field values to update (or JSON string)
    """
    # Parse field_values if it's a string (from JSON)
    if isinstance(field_values, str):
        import json
        field_values = json.loads(field_values)

    # Validate doctype is a valid ticket type
    valid_doctypes = list(TICKET_DOCTYPES.values())
    if ticket_doctype not in valid_doctypes:
        frappe.throw(f"Invalid ticket doctype: {ticket_doctype}")

    ticket = frappe.get_doc(ticket_doctype, ticket_name)

    for field, value in field_values.items():
        ticket.set(field, value)

    ticket.save(ignore_permissions=True)
    frappe.db.commit()

    frappe.logger().info(f"Saved {ticket_doctype} {ticket_name} with values: {field_values}")

    return ticket.as_dict()


def get_ticket_doctype(issue_type):
    """Get the ticket doctype name for a given issue type"""
    return TICKET_DOCTYPES.get(issue_type)
