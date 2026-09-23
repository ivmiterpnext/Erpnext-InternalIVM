"""Integration tests for ivm.client_portal.event_handlers.service_quote"""

from unittest.mock import call, patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite


def _make_contact(first_name, user=None):
	"""Create a Contact document."""
	return frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"user": user,
		}
	).insert(ignore_permissions=True)


def _make_service_quote(contact, signers=None):
	"""Create a Service Quote document (not submitted).

	Args:
	    contact: Contact name for the primary contact
	    signers: List of dicts with 'contact' key, or None for empty signers

	Returns:
	    Inserted (but not submitted) Service Quote document
	"""
	signer_rows = []
	if signers:
		signer_rows = [
			{
				"contact": s["contact"],
				"signature_method": "Portal Checkbox",
				"status": "Pending",
			}
			for s in signers
		]

	doc = frappe.get_doc(
		{
			"doctype": "Service Quote",
			"contact": contact,
			"sales_representative": "Administrator",
			"customer": "_Test Customer",
			"signers": signer_rows,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestServiceQuoteOnSubmit(ERPNextTestSuite):
	"""on_submit event handler for Service Quote"""

	@patch("ivm.client_portal.services.provisioning.ensure_portal_user")
	def test_no_signers_creates_one_with_contact(self, mock_ensure):
		"""No existing signers → creates one row with doc.contact, Portal Checkbox, Pending"""
		contact = _make_contact("NoSigners")
		doc = _make_service_quote(contact.name, signers=None)

		doc.submit()

		# Verify exactly one signer row exists
		signers = frappe.get_all(
			"Service Quote Signer",
			filters={"parent": doc.name},
			fields=["name", "contact", "signature_method", "status"],
		)
		self.assertEqual(len(signers), 1)
		self.assertEqual(signers[0]["contact"], contact.name)
		self.assertEqual(signers[0]["signature_method"], "Portal Checkbox")
		self.assertEqual(signers[0]["status"], "Pending")

		# Verify ensure_portal_user called once with that contact
		mock_ensure.assert_called_once_with(contact=contact.name, async_=False)

	@patch("ivm.client_portal.services.provisioning.ensure_portal_user")
	def test_existing_signers_no_new_row_added(self, mock_ensure):
		"""Existing signers → no new row added, ensure_portal_user called for each"""
		c1 = _make_contact("ExistingSigner1")
		c2 = _make_contact("ExistingSigner2")
		primary_contact = _make_contact("PrimaryContact")

		doc = _make_service_quote(
			primary_contact.name,
			signers=[{"contact": c1.name}, {"contact": c2.name}],
		)
		initial_signer_count = len(doc.signers)

		doc.submit()

		# Verify signer count unchanged
		signers = frappe.get_all(
			"Service Quote Signer",
			filters={"parent": doc.name},
		)
		self.assertEqual(len(signers), initial_signer_count)
		self.assertEqual(len(signers), 2)

		# Verify ensure_portal_user called once per signer
		self.assertEqual(mock_ensure.call_count, 2)
		mock_ensure.assert_any_call(contact=c1.name, async_=False)
		mock_ensure.assert_any_call(contact=c2.name, async_=False)

	@patch("ivm.client_portal.services.provisioning.ensure_portal_user")
	def test_duplicate_contact_in_signers_called_twice(self, mock_ensure):
		"""Two signers with same contact → ensure_portal_user called twice (no dedup)"""
		shared_contact = _make_contact("SharedContact")
		primary_contact = _make_contact("PrimaryContact2")

		doc = _make_service_quote(
			primary_contact.name,
			signers=[
				{"contact": shared_contact.name},
				{"contact": shared_contact.name},
			],
		)

		doc.submit()

		# Verify ensure_portal_user called twice with same contact
		self.assertEqual(mock_ensure.call_count, 2)
		mock_ensure.assert_any_call(contact=shared_contact.name, async_=False)
		# Second call also with same contact
		calls = mock_ensure.call_args_list
		self.assertEqual(calls[0], call(contact=shared_contact.name, async_=False))
		self.assertEqual(calls[1], call(contact=shared_contact.name, async_=False))

	@patch("ivm.client_portal.services.provisioning.ensure_portal_user")
	def test_status_set_to_sent_via_db_set_value(self, mock_ensure):
		"""After submit, status set to 'Sent' via db.set_value (not doc.save)"""
		contact = _make_contact("StatusTest")
		doc = _make_service_quote(contact.name, signers=None)

		doc.submit()

		# In-memory doc.status may still show old value (not reloaded)
		# This demonstrates the db.set_value vs doc.save distinction

		# DB value is "Sent"
		db_status = frappe.db.get_value("Service Quote", doc.name, "status")
		self.assertEqual(db_status, "Sent")

		# Reload and confirm it now reads "Sent"
		doc.reload()
		self.assertEqual(doc.status, "Sent")
