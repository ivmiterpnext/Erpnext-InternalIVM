import frappe 
import re

@frappe.whitelist()
def seting_to_email():
    Issue_Rec =  frappe.db.get_list('Issue', pluck='name')
    for i in Issue_Rec:
        doc = frappe.get_doc('Issue', i)
        if doc.issue_type == None:
            subject = frappe.db.get_list("Communication",filters={'subject':doc.subject},fields=['recipients'],pluck='recipients')
            if subject:
                Str = subject[0]
                email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
                email_matches = re.findall(email_regex, Str)
                if email_matches:
                    Issue_Type = frappe.db.get_list("Email Account",filters={'email_id':email_matches[0]},fields=['custom_issue_type'],pluck="custom_issue_type")
                    if Issue_Type:
                        doc.issue_type = Issue_Type[0]
                        doc.save(ignore_permissions=True)
