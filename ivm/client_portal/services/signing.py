"""
Handle Service Quote acceptance and decline responses.
"""

import frappe


@frappe.whitelist()
def accept_quote(service_quote, signer, typed_name):
	"""
	Accept a Service Quote as a signer.

	Args:
	    service_quote: Service Quote name
	    signer: Service Quote Signer child row name
	    typed_name: Name typed by the signer
	"""
	return _process_signer_response(service_quote, signer, "Accepted", typed_name)


@frappe.whitelist()
def decline_quote(service_quote, signer, typed_name, reason=None):
	"""
	Decline a Service Quote as a signer.

	Args:
	    service_quote: Service Quote name
	    signer: Service Quote Signer child row name
	    typed_name: Name typed by the signer
	    reason: Optional free-text reason for declining
	"""
	return _process_signer_response(service_quote, signer, "Declined", typed_name, reason=reason)


def _process_signer_response(service_quote, signer, response, typed_name, reason=None):
	"""
	Process a signer's response (accept/decline).

	Validates:
	- Quote is submitted (docstatus == 1)
	- Signer row exists
	- Current user's Contact matches the signer's contact
	- Signer status is still Pending

	Then delegates to status_rollup.resolve_signer_response.
	"""
	# Load and validate quote
	quote_doc = frappe.get_doc("Service Quote", service_quote)
	if quote_doc.docstatus != 1:
		frappe.throw("Service Quote must be submitted to accept/decline.")

	if quote_doc.status in ("Cancelled", "Expired"):
		frappe.throw(f"This quote is {quote_doc.status.lower()} and can no longer be responded to.")

	# Find signer row
	signer_row = None
	for row in quote_doc.signers or []:
		if row.name == signer:
			signer_row = row
			break

	if not signer_row:
		frappe.throw("Signer not found in this quote.")

	# Verify current user's contact matches signer's contact
	current_user_contact = frappe.db.get_value("Contact", {"user": frappe.session.user}, "name")
	if current_user_contact != signer_row.contact:
		frappe.throw("You are not authorized to respond for this signer.", exc=frappe.PermissionError)

	# Verify signer status is still Pending
	if signer_row.status != "Pending":
		frappe.throw(f"This signer has already responded with status: {signer_row.status}")

	# Get request IP
	request_ip = frappe.local.request_ip if hasattr(frappe.local, "request_ip") else ""

	# Delegate to status rollup
	from ivm.client_portal.utils.status_rollup import resolve_signer_response

	resolve_signer_response(quote_doc, signer, response, typed_name, request_ip, reason=reason)

	return {"status": "ok", "message": f"Quote {response.lower()} successfully"}
