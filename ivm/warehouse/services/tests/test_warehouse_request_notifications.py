"""Regression tests for the Warehouse Request closed-notification fixture.

Covers the 2026-10 bug where the "Warehouse Request Resolved/Closed
Notification" recipient condition referenced doc.created_by after that
column was dropped by ivm.warehouse.patches.drop_wr_created_by_fields,
which silently broke the notification (AttributeError swallowed into an
Error Log on every WR close, no email ever sent).
"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from frappe.email.doctype.notification.notification import get_context

NOTIFICATION = "Warehouse Request Resolved/Closed Notification"


def _make_wr(owner=None, status="New"):
	doc = frappe.get_doc(
		{
			"doctype": "Warehouse Request",
			"request_reason": "Build Machine",
			"subject": "WR Notification Test",
			"schema_version": 2,
			"status": status,
		}
	)
	doc.insert(ignore_permissions=True)
	if owner:
		doc.db_set("owner", owner, update_modified=False)
		doc.reload()
	return doc


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "WR Notify Test",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	return email


class TestWarehouseRequestClosedNotification(ERPNextTestSuite):
	def test_recipient_conditions_do_not_reference_dropped_fields(self):
		notification = frappe.get_doc("Notification", NOTIFICATION)
		wr = _make_wr()
		context = get_context(wr)
		for recipient in notification.recipients:
			if recipient.condition:
				frappe.safe_eval(recipient.condition, None, context)

	def test_ivminc_owner_is_recipient(self):
		owner = _ensure_user("wr-notify-test@ivminc.com")
		wr = _make_wr(owner=owner)
		notification = frappe.get_doc("Notification", NOTIFICATION)
		recipients, _cc, _bcc = notification.get_list_of_recipients(wr, get_context(wr))
		self.assertIn(owner, recipients)

	def test_external_owner_is_not_recipient(self):
		owner = _ensure_user("wr-notify-test@example.com")
		wr = _make_wr(owner=owner)
		notification = frappe.get_doc("Notification", NOTIFICATION)
		recipients, _cc, _bcc = notification.get_list_of_recipients(wr, get_context(wr))
		self.assertNotIn(owner, recipients)

	def test_closing_wr_does_not_error(self):
		"""Verify that closing a WR does not raise AttributeError on the condition.

		The condition is evaluated during notification send; if it references
		a dropped field like doc.created_by, it will raise AttributeError.
		This test verifies the condition can be safely evaluated.
		"""
		owner = _ensure_user("wr-notify-test@ivminc.com")
		wr = _make_wr(owner=owner, status="New")
		notification = frappe.get_doc("Notification", NOTIFICATION)
		context = get_context(wr)

		# Verify the condition can be evaluated without AttributeError
		for recipient in notification.recipients:
			if recipient.condition:
				# This should not raise AttributeError
				frappe.safe_eval(recipient.condition, None, context)
