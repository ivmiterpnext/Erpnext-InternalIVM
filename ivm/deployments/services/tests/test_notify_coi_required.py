"""Integration tests for ivm.deployments.services.notify_coi_required"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.notify_coi_required import send_notification


def _make_deployment(coi_required):
	return frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"COI Test {frappe.generate_hash(length=6)}",
			"company": "_Test Company",
			"coi_required": coi_required,
		}
	).insert(ignore_permissions=True)


class TestSendNotification(ERPNextTestSuite):
	# coi_required is a Select field (options: "", "Yes", "No") on Project,
	# not a Checkbox -- confirmed via schema; "Yes"/"No" strings are correct here.
	# frappe.sendmail itself is mocked since it requires a configured outgoing
	# Email Account to queue anything at all (an environment concern, not part
	# of send_notification's own conditional logic being tested here).
	def test_sends_email_when_coi_required_truthy(self):
		deployment = _make_deployment(coi_required="Yes")
		with patch("frappe.sendmail") as mock_sendmail:
			send_notification(deployment)
		mock_sendmail.assert_called_once()
		call_kwargs = mock_sendmail.call_args.kwargs
		self.assertIn(deployment.name, call_kwargs["subject"])

	def test_no_email_when_coi_not_required(self):
		deployment = _make_deployment(coi_required="No")
		with patch("frappe.sendmail") as mock_sendmail:
			send_notification(deployment)
		mock_sendmail.assert_not_called()
