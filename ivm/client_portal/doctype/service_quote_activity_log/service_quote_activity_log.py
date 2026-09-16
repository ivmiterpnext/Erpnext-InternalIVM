"""
Service Quote Activity Log doctype controller.

Read-only audit trail of portal page views, PDF downloads, and accept/decline
responses (including an optional decline reason) for a Service Quote. Rows
are only ever inserted server-side (ignore_permissions=True) via
ivm.client_portal.utils.activity_log.log_quote_activity — no role is granted
create permission on this doctype directly.
"""

from frappe.model.document import Document


class ServiceQuoteActivityLog(Document):
    pass
