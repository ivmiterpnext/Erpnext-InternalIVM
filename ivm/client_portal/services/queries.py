"""
Custom query functions for Service Quote form filtering.
"""

import frappe
from frappe.desk.reportview import get_match_cond


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def deal_contact_query(doctype, txt, searchfield, start, page_len, filters):
	"""Filter Contact link-field options to only contacts related to a specific CRM Deal
	(via CRM Deal's own `contacts` child table), rather than the standard Dynamic Link
	mechanism — Contact has no Dynamic Link relationship to CRM Organization in this app,
	so this is the only reliable way to scope contacts to a deal's business regardless of
	whether it's New or Existing Business.
	"""
	doctype = "Contact"
	if not frappe.get_meta(doctype).get_field(searchfield) and searchfield not in frappe.db.DEFAULT_COLUMNS:
		return []

	crm_deal = filters.pop("crm_deal", None)
	if not crm_deal:
		return []

	return frappe.db.sql(
		f"""select
			`tabContact`.name, `tabContact`.full_name, `tabContact`.company_name
		from
			`tabContact`, `tabCRM Contacts`
		where
			`tabCRM Contacts`.parent = %(crm_deal)s and
			`tabCRM Contacts`.contact = `tabContact`.name and
			`tabContact`.`{searchfield}` like %(txt)s
			{get_match_cond(doctype)}
		order by
			if(locate(%(_txt)s, `tabContact`.full_name), locate(%(_txt)s, `tabContact`.company_name), 99999),
			`tabContact`.idx desc, `tabContact`.full_name
		limit %(start)s, %(page_len)s """,
		{
			"txt": "%" + txt + "%",
			"_txt": txt.replace("%", ""),
			"start": start,
			"page_len": page_len,
			"crm_deal": crm_deal,
		},
	)
