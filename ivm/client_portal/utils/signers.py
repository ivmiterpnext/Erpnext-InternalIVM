"""
Shared helper for resolving the Service Quote Signer row belonging to the
current (or given) session user, used by both the portal page controller and
the PDF download endpoint.
"""

import frappe


def get_signer_row_for_user(quote_doc, user=None):
	"""
	Return the Service Quote Signer child row whose contact matches the
	given user's linked Contact, or None if no match / no linked Contact.
	"""
	user = user or frappe.session.user
	contact_name = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact_name:
		return None

	for row in quote_doc.signers or []:
		if row.contact == contact_name:
			return row

	return None
