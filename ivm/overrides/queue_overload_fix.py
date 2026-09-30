"""Monkey-patch for frappe.utils.background_jobs._check_queue_size.

Frappe core bug: _check_queue_size calls frappe.has_permission("System Health Report")
with throw=False, but SystemHealthReport.load_from_db() unconditionally calls
frappe.only_for("System Manager"), raising PermissionError for non-System-Manager
users (including Guest, which is the session user for HubSpot webhook requests).
This shadows the intended QueueOverloaded exception with a raw PermissionError.

This patch wraps the has_permission call in a try/except so that on any permission
evaluation failure, primary_action defaults to None and QueueOverloaded is raised
as designed.

Remove this patch when Frappe core fixes the bug upstream.
"""

import frappe
from frappe.utils import cint


def _check_queue_size_patched(q):
	from frappe.utils.background_jobs import MAX_QUEUED_JOBS, _site_count

	max_jobs = cint(frappe.conf.max_queued_jobs) or MAX_QUEUED_JOBS
	max_jobs += _site_count() * 50

	if cint(q.count) >= max_jobs:
		primary_action = None
		try:
			if frappe.has_permission("System Health Report"):
				primary_action = {
					"label": "Monitor System Health",
					"client_action": "frappe.set_route",
					"args": ["Form", "System Health Report"],
				}
		except Exception:
			pass

		frappe.throw(
			frappe._("Too many queued background jobs ({0}). Please retry after some time.").format(max_jobs),
			title=frappe._("Queue Overloaded"),
			exc=frappe.QueueOverloaded,
			primary_action=primary_action,
		)


def apply() -> None:
	"""Replace _check_queue_size in the background_jobs module."""
	import frappe.utils.background_jobs as bg

	bg._check_queue_size = _check_queue_size_patched
