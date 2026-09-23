"""
Record Service Quote portal activity — page views, PDF downloads, and
accept/decline responses (with an optional decline reason) — for audit
purposes.

Writes are best-effort: a logging failure must never block a signer from
viewing, downloading, or responding to their quote, so insert errors are
swallowed and reported via frappe.log_error rather than propagated.
"""

import frappe
from frappe.utils import now_datetime


def log_quote_activity(quote_doc, signer_row, event_type, reason=None):
	"""
	Insert a Service Quote Activity Log row.

	Args:
	    quote_doc: Service Quote document object
	    signer_row: Service Quote Signer child row for the current user
	        (may be None; contact will be left blank in that case)
	    event_type: "View Page", "View PDF", "Accepted", or "Declined"
	    reason: Optional free-text reason, only meaningful when
	        event_type == "Declined"
	"""
	try:
		request_ip = getattr(frappe.local, "request_ip", None) or ""

		frappe.get_doc(
			{
				"doctype": "Service Quote Activity Log",
				"service_quote": quote_doc.name,
				"contact": signer_row.contact if signer_row else None,
				"user": frappe.session.user,
				"event_type": event_type,
				"event_time": now_datetime(),
				"ip_address": request_ip,
				"reason": reason,
			}
		).insert(ignore_permissions=True)
		frappe.local.flags.commit = True
	except Exception:
		frappe.log_error(
			title="Service Quote activity log insert failed",
			message=frappe.get_traceback(),
			reference_doctype="Service Quote",
			reference_name=quote_doc.name,
		)
