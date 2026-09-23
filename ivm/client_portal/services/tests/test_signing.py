"""Integration tests for ivm.client_portal.services.signing"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.signing import accept_quote, decline_quote

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


def _make_signer_contact(first_name, user):
	"""Create a Contact as the sole contact for the given user.

	Unlinks any other Contacts already pointing at this user so that
	frappe.db.get_value("Contact", {"user": user}) deterministically
	returns this contact — critical because _process_signer_response
	uses that exact lookup for its authorization check.
	"""
	for existing in frappe.get_all("Contact", {"user": user}, pluck="name"):
		frappe.db.set_value("Contact", existing, "user", None)
	return frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"user": user,
		}
	).insert(ignore_permissions=True)


def _make_submitted_quote(signer_contacts):
	"""Create and submit a Service Quote with the given signer contacts.

	Returns (quote_doc, [signer_row_name, ...]).
	"""
	top_contact = _make_contact(f"TopSG-{frappe.generate_hash(length=6)}")
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
class TestAcceptDeclineQuote(ERPNextTestSuite):
	"""accept_quote / decline_quote validation and happy paths"""

	def setUp(self):
		super().setUp()
		self._original_user = frappe.session.user

	def tearDown(self):
		frappe.set_user(self._original_user)
		super().tearDown()

	def test_throws_when_quote_not_submitted(self, _mock_notify):
		sc = _make_signer_contact("SG Draft", TEST_USER_1)
		doc = frappe.get_doc(
			{
				"doctype": "Service Quote",
				"contact": sc.name,
				"sales_representative": "Administrator",
				"customer": "_Test Customer",
				"signers": [{"contact": sc.name, "status": "Pending"}],
			}
		)
		doc.insert(ignore_permissions=True)

		frappe.set_user(TEST_USER_1)
		with self.assertRaises(frappe.ValidationError):
			accept_quote(doc.name, doc.signers[0].name, "John")

	def test_throws_when_quote_cancelled(self, _mock_notify):
		sc = _make_signer_contact("SG Cancel", TEST_USER_1)
		quote, signer_names = _make_submitted_quote([sc])
		frappe.db.set_value("Service Quote", quote.name, "status", "Cancelled")

		frappe.set_user(TEST_USER_1)
		with self.assertRaises(frappe.ValidationError):
			accept_quote(quote.name, signer_names[0], "John")

	def test_throws_when_signer_not_found(self, _mock_notify):
		sc = _make_signer_contact("SG NoFind", TEST_USER_1)
		quote, _ = _make_submitted_quote([sc])

		frappe.set_user(TEST_USER_1)
		with self.assertRaises(frappe.ValidationError):
			accept_quote(quote.name, "nonexistent-row-name", "John")

	def test_throws_when_contact_mismatch(self, _mock_notify):
		sc = _make_signer_contact("SG Mismatch", TEST_USER_1)
		quote, signer_names = _make_submitted_quote([sc])

		frappe.set_user(TEST_USER_2)
		with self.assertRaises(frappe.PermissionError):
			accept_quote(quote.name, signer_names[0], "John")

	def test_throws_when_already_responded(self, _mock_notify):
		sc = _make_signer_contact("SG Already", TEST_USER_1)
		quote, signer_names = _make_submitted_quote([sc])
		frappe.db.set_value(
			"Service Quote Signer",
			signer_names[0],
			"status",
			"Accepted",
		)

		frappe.set_user(TEST_USER_1)
		with self.assertRaises(frappe.ValidationError):
			accept_quote(quote.name, signer_names[0], "John")

	def test_accept_happy_path(self, _mock_notify):
		sc = _make_signer_contact("SG Happy", TEST_USER_1)
		quote, signer_names = _make_submitted_quote([sc])

		frappe.set_user(TEST_USER_1)
		result = accept_quote(quote.name, signer_names[0], "John Doe")

		self.assertEqual(result["status"], "ok")
		self.assertEqual(
			frappe.db.get_value("Service Quote", quote.name, "status"),
			"Accepted",
		)

	@patch("ivm.client_portal.utils.status_rollup.resolve_signer_response")
	def test_decline_passes_reason(self, mock_resolve, _mock_notify):
		sc = _make_signer_contact("SG Reason", TEST_USER_1)
		quote, signer_names = _make_submitted_quote([sc])

		frappe.set_user(TEST_USER_1)
		decline_quote(quote.name, signer_names[0], "Jane Doe", reason="Too expensive")

		mock_resolve.assert_called_once()
		_args, kwargs = mock_resolve.call_args
		self.assertEqual(_args[2], "Declined")
		self.assertEqual(kwargs["reason"], "Too expensive")
