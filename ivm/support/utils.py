import frappe


def fetch_customer_name_and_contact(sender_name):
    try:
        contact_name = frappe.db.sql("""SELECT DISTINCT c.name AS contact_name, dl.link_name AS customer_name
                                   FROM `tabContact` c
                                   INNER JOIN `tabContact Email` ce ON c.name = ce.parent
                                   LEFT JOIN `tabDynamic Link` dl ON c.name = dl.parent AND dl.link_doctype = 'Customer'
                                   WHERE ce.email_id = %s""", (sender_name,), as_dict=True)
        return contact_name[0]
    except Exception as e:
        pass
