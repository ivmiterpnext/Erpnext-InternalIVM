"""
Send notifications for Service Quote signer responses.
"""

import frappe


def notify_assigned_rep(service_quote_name, signer_row_name, response, reason=None):
	"""
	Send an email to the assigned rep when a signer responds.

	Args:
	    service_quote_name: Service Quote name
	    signer_row_name: Service Quote Signer child row name
	    response: "Accepted" or "Declined"
	    reason: Optional free-text reason, only meaningful when response == "Declined"
	"""
	try:
		# Get quote and signer details
		quote = frappe.get_doc("Service Quote", service_quote_name)
		signer = None
		for row in quote.signers or []:
			if row.name == signer_row_name:
				signer = row
				break

		if not signer:
			return

		# Get signer contact name
		contact_name = frappe.db.get_value("Contact", signer.contact, "first_name")
		signer_name = signer.accepted_name or contact_name or "Unknown"

		# Get sales representative email
		rep_email = frappe.db.get_value("User", quote.sales_representative, "email")
		if not rep_email:
			return

		# Build email
		subject = f"Service Quote {service_quote_name}: {response}"
		reason_html = ""
		if reason:
			reason_html = f"<p><strong>Reason provided:</strong> {frappe.utils.escape_html(reason)}</p>"

		message = f"""
<p>Hi,</p>

<p>{signer_name} has <strong>{response.lower()}</strong> the Service Quote <a href="/app/service-quote/{service_quote_name}">{service_quote_name}</a>.</p>
{reason_html}
<p>Please review the quote status and take any necessary follow-up actions.</p>

<p>Best regards,<br/>IVM Portal</p>
"""

		frappe.sendmail(
			recipients=[rep_email],
			subject=subject,
			message=message,
		)
	except Exception as e:
		frappe.log_error(
			f"Failed to send notification for quote {service_quote_name}: {e!s}",
			title="Service Quote Notification Error",
		)
