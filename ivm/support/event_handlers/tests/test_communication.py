from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.support.event_handlers.communication import SUPPORT_ISSUE_TYPES, on_update


class TestCommunicationOnUpdate(FrappeTestCase):
	"""Test suite for ivm.support.event_handlers.communication.on_update"""

	def setUp(self):
		super().setUp()
		# Create a test Issue Type for support issues
		if not frappe.db.exists("Issue Type", "Support"):
			frappe.get_doc({"doctype": "Issue Type", "name": "Support"}).insert()

		# Create a non-support Issue Type
		if not frappe.db.exists("Issue Type", "Other"):
			frappe.get_doc({"doctype": "Issue Type", "name": "Other"}).insert()

	def test_non_issue_reference_doctype_returns_immediately(self):
		"""Case 1: Non-'Issue' reference_doctype should return without side effects"""
		# Create a mock Communication with reference_doctype != "Issue"
		mock_doc = MagicMock()
		mock_doc.reference_doctype = "Task"
		mock_doc.email_account = None
		mock_doc.sender = "test@example.com"

		# Should not raise and should return immediately
		result = on_update(mock_doc, None)
		self.assertIsNone(result)

	def test_issue_reference_no_email_account_unchanged(self):
		"""Case 2: Issue reference but no email_account set → Issue fields untouched"""
		# Create a real Issue
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "Test Issue",
				"description": "Original description",
				"issue_type": "IT",
			}
		).insert()

		# Create a Communication referencing the Issue with no email_account
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "test@example.com",
				"content": "New content",
				"email_account": None,
			}
		).insert()

		# Store original values
		original_desc = issue.description
		original_type = issue.issue_type

		# Run on_update
		on_update(comm, None)

		# Reload and verify unchanged
		issue.reload()
		self.assertEqual(issue.description, original_desc)
		self.assertEqual(issue.issue_type, original_type)

	def test_support_issue_type_sets_customer_and_contact(self):
		"""Case 3: Support issue type with customer/contact data → fields set"""
		# Create Customer Group and real Customer first
		if not frappe.db.exists("Customer Group", "_Test Customer Group"):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": "_Test Customer Group",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		real_customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"Test Customer {frappe.generate_hash(length=6)}",
				"customer_type": "Individual",
				"customer_group": "_Test Customer Group",
			}
		).insert(ignore_permissions=True)

		# Create real Contact
		real_contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": f"TestContact{frappe.generate_hash(length=6)}",
			}
		).insert(ignore_permissions=True)

		# Create Email Account with IMAP folder pointing to Support issue type
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"support-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Support"}],
			}
		).insert()

		# Create Issue
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Support Issue", "issue_type": "IT"}).insert()

		# Create Communication
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "customer@example.com",
				"content": "Help needed",
				"email_account": email_account.name,
			}
		).insert()

		# Mock fetch_customer_name_and_contact to return real customer data
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = {"customer_name": real_customer.name, "contact_name": real_contact.name}

			on_update(comm, None)

		# Verify Issue was updated
		issue.reload()
		self.assertEqual(issue.customer, real_customer.name)
		self.assertEqual(issue.contact_name, real_contact.name)
		self.assertEqual(issue.issue_type, "Support")

	def test_non_support_issue_type_skips_customer_contact(self):
		"""Case 4: Non-support issue type → issue_type set but customer/contact NOT touched"""
		# Create Customer Group and real Customer first
		if not frappe.db.exists("Customer Group", "_Test Customer Group"):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": "_Test Customer Group",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		orig_customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"Original Customer {frappe.generate_hash(length=6)}",
				"customer_type": "Individual",
				"customer_group": "_Test Customer Group",
			}
		).insert(ignore_permissions=True)

		orig_contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": f"OrigContact{frappe.generate_hash(length=6)}",
			}
		).insert(ignore_permissions=True)

		# Create Email Account with IMAP folder pointing to non-support issue type
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"other-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Other"}],
			}
		).insert()

		# Create Issue with pre-set customer/contact
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "Other Issue",
				"customer": orig_customer.name,
				"contact_name": orig_contact.name,
				"issue_type": "IT",
			}
		).insert()

		# Create Communication
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "someone@example.com",
				"content": "Some content",
				"email_account": email_account.name,
			}
		).insert()

		# Mock fetch_customer_name_and_contact (should NOT be called)
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			on_update(comm, None)
			# Verify fetch was never called
			mock_fetch.assert_not_called()

		# Verify Issue: issue_type set, but customer/contact unchanged
		issue.reload()
		self.assertEqual(issue.issue_type, "Other")
		self.assertEqual(issue.customer, orig_customer.name)
		self.assertEqual(issue.contact_name, orig_contact.name)

	def test_fetch_customer_returns_none_skips_customer_contact(self):
		"""Case 5: fetch_customer_name_and_contact returns None → customer/contact left unchanged"""
		# Create Customer Group and real Customer first
		if not frappe.db.exists("Customer Group", "_Test Customer Group"):
			frappe.get_doc(
				{
					"doctype": "Customer Group",
					"customer_group_name": "_Test Customer Group",
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

		existing_customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"Existing Customer {frappe.generate_hash(length=6)}",
				"customer_type": "Individual",
				"customer_group": "_Test Customer Group",
			}
		).insert(ignore_permissions=True)

		existing_contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": f"ExistContact{frappe.generate_hash(length=6)}",
			}
		).insert(ignore_permissions=True)

		# Create Email Account with support issue type
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"support2-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Support"}],
			}
		).insert()

		# Create Issue with pre-set customer/contact
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "Support Issue",
				"customer": existing_customer.name,
				"contact_name": existing_contact.name,
				"issue_type": "IT",
			}
		).insert()

		# Create Communication
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "unknown@example.com",
				"content": "Help",
				"email_account": email_account.name,
			}
		).insert()

		# Mock fetch to return None
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = None
			on_update(comm, None)

		# Verify customer/contact unchanged
		issue.reload()
		self.assertEqual(issue.customer, existing_customer.name)
		self.assertEqual(issue.contact_name, existing_contact.name)
		self.assertEqual(issue.issue_type, "Support")

	def test_first_communication_overwrites_description(self):
		"""Case 6: First Communication (only 1 total) → description overwritten"""
		# Create Email Account
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"support3-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Support"}],
			}
		).insert()

		# Create Issue with original description
		issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Test", "description": "Original description", "issue_type": "IT"}
		).insert()

		# Create first Communication
		comm1 = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "test@example.com",
				"content": "First message content",
				"email_account": email_account.name,
			}
		).insert()

		# Mock fetch
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = None
			on_update(comm1, None)

		# Verify description was overwritten
		issue.reload()
		self.assertEqual(issue.description, "First message content")

	def test_second_communication_does_not_overwrite_description(self):
		"""Case 7: Second Communication (2 total) → description NOT overwritten"""
		# Create Email Account
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"support4-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Support"}],
			}
		).insert()

		# Create Issue
		issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Test", "description": "Original description", "issue_type": "IT"}
		).insert()

		# Create first Communication
		comm1 = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "test1@example.com",
				"content": "First message",
				"email_account": email_account.name,
			}
		).insert()

		# Create second Communication
		comm2 = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "test2@example.com",
				"content": "Second message",
				"email_account": email_account.name,
			}
		).insert()

		# Process first communication
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = None
			on_update(comm1, None)

		issue.reload()
		first_desc = issue.description

		# Process second communication
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = None
			on_update(comm2, None)

		# Verify description unchanged (still first message)
		issue.reload()
		self.assertEqual(issue.description, first_desc)
		self.assertNotEqual(issue.description, "Second message")

	def test_attachment_creates_file_on_issue(self):
		"""Case 8: Communication with attachment → File created on Issue"""
		# Create Email Account
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"support5-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Support"}],
			}
		).insert()

		# Create Issue
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Test", "issue_type": "IT"}).insert()

		# Create Communication first
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "test@example.com",
				"content": "Message with attachment",
				"email_account": email_account.name,
			}
		).insert()

		# Create a File attached to the Communication with real content
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "test_attachment.txt",
				"attached_to_doctype": "Communication",
				"attached_to_name": comm.name,
				"is_private": 1,
				"content": b"test file content",
			}
		).insert()

		# Reload communication to ensure get_attachments() picks up the file
		comm.reload()

		# Mock fetch
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = None
			on_update(comm, None)

		# Verify File now exists attached to Issue
		issue_file = frappe.db.exists(
			"File",
			{"file_url": file_doc.file_url, "attached_to_doctype": "Issue", "attached_to_name": issue.name},
		)
		self.assertTrue(issue_file)

	def test_attachment_deduplication(self):
		"""Case 8b: Same file_url already attached to Issue → no duplicate created"""
		# Create Email Account
		email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"support6-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [{"folder_name": "INBOX", "custom_issue_type": "Support"}],
			}
		).insert()

		# Create Issue
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Test", "issue_type": "IT"}).insert()

		# Create a File already attached to the Issue with real content
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "existing.txt",
				"attached_to_doctype": "Issue",
				"attached_to_name": issue.name,
				"is_private": 1,
				"content": b"existing file content",
			}
		).insert()

		# Create Communication with same file_url
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"reference_doctype": "Issue",
				"reference_name": issue.name,
				"sender": "test@example.com",
				"content": "Message",
				"email_account": email_account.name,
			}
		).insert()

		# Attach file to Communication too with same file_url
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "existing.txt",
				"attached_to_doctype": "Communication",
				"attached_to_name": comm.name,
				"is_private": 1,
				"content": b"existing file content",
				"file_url": file_doc.file_url,
			}
		).insert()

		# Count files before
		count_before = frappe.db.count(
			"File",
			{"file_url": file_doc.file_url, "attached_to_doctype": "Issue", "attached_to_name": issue.name},
		)

		# Mock fetch
		with patch("ivm.support.event_handlers.communication.fetch_customer_name_and_contact") as mock_fetch:
			mock_fetch.return_value = None
			on_update(comm, None)

		# Count files after - should be same (no duplicate)
		count_after = frappe.db.count(
			"File",
			{"file_url": file_doc.file_url, "attached_to_doctype": "Issue", "attached_to_name": issue.name},
		)
		self.assertEqual(count_before, count_after)

	def test_exception_logged_not_raised(self):
		"""Case 9: Exception inside try block → logged via frappe.log_error, not raised"""
		# Create a real Email Account first
		real_email_account = frappe.get_doc(
			{
				"doctype": "Email Account",
				"email_id": f"exc-{frappe.generate_hash(length=8)}@test.com",
				"imap_folder": [
					{
						"folder_name": "INBOX",
						"custom_issue_type": "Support",
					}
				],
			}
		).insert()

		# Create a mock Communication
		mock_doc = MagicMock()
		mock_doc.reference_doctype = "Issue"
		mock_doc.reference_name = "nonexistent-issue"
		mock_doc.email_account = real_email_account.name
		mock_doc.sender = "test@example.com"
		mock_doc.content = "Test"
		mock_doc.get_attachments.return_value = []

		# Patch frappe.get_doc to raise for Issue doctype
		def side_effect_get_doc(doctype, name):
			if doctype == "Issue":
				raise ValueError("Simulated error")
			return MagicMock()

		with patch(
			"ivm.support.event_handlers.communication.frappe.get_doc", side_effect=side_effect_get_doc
		):
			with patch("ivm.support.event_handlers.communication.frappe.log_error") as mock_log:
				# Should not raise
				on_update(mock_doc, None)
				# Verify log_error was called
				mock_log.assert_called_once()
