"""Integration tests for ivm.client_portal.utils.status_rollup"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.utils.status_rollup import resolve_signer_response

TEST_USER_1 = "test@example.com"
TEST_USER_2 = "test1@example.com"


def _make_contact(first_name, user=None):
	return frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"user": user,
		}
	).insert(ignore_permissions=True)


def _make_submitted_quote(signer_contacts):
	"""Create and submit a Service Quote with the given signer contacts.

	Mocks out the on_submit event handler (which provisions portal users and
	sets status to Sent) and manually sets the required post-submit state.

	Returns (quote_doc, [signer_row_name, ...]).
	"""
	top_contact = _make_contact(f"TopSR-{frappe.generate_hash(length=6)}")
	signers = [{"contact": c.name, "status": "Pending"} for c in signer_contacts]
	doc = frappe.get_doc(
		{
			"doctype": "Service Quote",
			"contact": top_contact.name,
			"sales_representative": "Administrator",
			"customer": "_Test Customer",
			"signers": signers,
		}
	)
	doc.insert(ignore_permissions=True)

	with patch("ivm.client_portal.event_handlers.service_quote.on_submit"):
		doc.submit()

	frappe.db.set_value("Service Quote", doc.name, "status", "Sent")
	doc.reload()
	return doc, [r.name for r in doc.signers]


@patch("ivm.client_portal.utils.notifications.notify_assigned_rep")
class TestResolveSignerResponse(ERPNextTestSuite):
	"""resolve_signer_response"""

	def test_single_signer_accept_sets_accepted(self, _mock_notify):
		signer_contact = _make_contact("SR Accept", user=TEST_USER_1)
		quote, signer_names = _make_submitted_quote([signer_contact])

		resolve_signer_response(quote, signer_names[0], "Accepted", "John Doe", "127.0.0.1")

		self.assertEqual(
			frappe.db.get_value("Service Quote", quote.name, "status"),
			"Accepted",
		)
		signer_data = frappe.db.get_value(
			"Service Quote Signer",
			signer_names[0],
			["accepted_name", "status", "accepted_ip"],
			as_dict=True,
		)
		self.assertEqual(signer_data.accepted_name, "John Doe")
		self.assertEqual(signer_data.status, "Accepted")
		self.assertEqual(signer_data.accepted_ip, "127.0.0.1")

	def test_single_signer_decline_sets_needs_rep_review(self, _mock_notify):
		signer_contact = _make_contact("SR Decline", user=TEST_USER_1)
		quote, signer_names = _make_submitted_quote([signer_contact])

		resolve_signer_response(
			quote,
			signer_names[0],
			"Declined",
			"Jane Doe",
			"10.0.0.1",
			reason="Too expensive",
		)

		self.assertEqual(
			frappe.db.get_value("Service Quote", quote.name, "status"),
			"Needs Rep Review",
		)

	def test_multi_signer_partial_accept(self, _mock_notify):
		c1 = _make_contact("SR Multi1", user=TEST_USER_1)
		c2 = _make_contact("SR Multi2", user=TEST_USER_2)
		quote, signer_names = _make_submitted_quote([c1, c2])

		resolve_signer_response(quote, signer_names[0], "Accepted", "S1", "1.1.1.1")

		self.assertEqual(
			frappe.db.get_value("Service Quote", quote.name, "status"),
			"Partially Accepted",
		)

	def test_multi_signer_all_accept(self, _mock_notify):
		c1 = _make_contact("SR AllAcc1", user=TEST_USER_1)
		c2 = _make_contact("SR AllAcc2", user=TEST_USER_2)
		quote, signer_names = _make_submitted_quote([c1, c2])

		resolve_signer_response(quote, signer_names[0], "Accepted", "S1", "1.1.1.1")
		quote.reload()
		resolve_signer_response(quote, signer_names[1], "Accepted", "S2", "2.2.2.2")

		self.assertEqual(
			frappe.db.get_value("Service Quote", quote.name, "status"),
			"Accepted",
		)

	def test_multi_signer_decline_overrides_prior_accept(self, _mock_notify):
		c1 = _make_contact("SR Over1", user=TEST_USER_1)
		c2 = _make_contact("SR Over2", user=TEST_USER_2)
		quote, signer_names = _make_submitted_quote([c1, c2])

		resolve_signer_response(quote, signer_names[0], "Accepted", "S1", "1.1.1.1")
		quote.reload()
		resolve_signer_response(quote, signer_names[1], "Declined", "S2", "2.2.2.2")

		self.assertEqual(
			frappe.db.get_value("Service Quote", quote.name, "status"),
			"Needs Rep Review",
		)

	def test_activity_log_created(self, _mock_notify):
		signer_contact = _make_contact("SR Log", user=TEST_USER_1)
		quote, signer_names = _make_submitted_quote([signer_contact])

		resolve_signer_response(quote, signer_names[0], "Accepted", "Logger", "5.5.5.5")

		self.assertTrue(
			frappe.db.exists(
				"Service Quote Activity Log",
				{"service_quote": quote.name, "event_type": "Accepted"},
			)
		)

	def test_notify_assigned_rep_invoked(self, mock_notify):
		signer_contact = _make_contact("SR Notify", user=TEST_USER_1)
		quote, signer_names = _make_submitted_quote([signer_contact])

		resolve_signer_response(
			quote,
			signer_names[0],
			"Declined",
			"Notifier",
			"6.6.6.6",
			reason="Not interested",
		)

		mock_notify.assert_called_once_with(
			quote.name,
			signer_names[0],
			"Declined",
			reason="Not interested",
		)
