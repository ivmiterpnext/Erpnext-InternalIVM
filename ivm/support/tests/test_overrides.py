import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from ivm.support.overrides import CustomEmailAccount


class TestCustomEmailAccountSendAutoReply(FrappeTestCase):
    """Test suite for ivm.support.overrides.CustomEmailAccount.send_auto_reply"""

    def setUp(self):
        super().setUp()
        # Create a test Email Account
        self.email_account = frappe.get_doc({
            "doctype": "Email Account",
            "email_id": f"test-{frappe.generate_hash(length=8)}@example.com"
        }).insert()

    def test_single_communication_calls_super(self):
        """Case 1: Exactly 1 Communication with given reference → super().send_auto_reply called"""
        # Create a reference document (Issue)
        issue = frappe.get_doc({
            "doctype": "Issue",
            "subject": "Test Issue"
        }).insert()
        
        # Create exactly 1 Communication
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "reference_doctype": "Issue",
            "reference_name": issue.name,
            "sender": "test@example.com",
            "content": "Test message"
        }).insert()
        
        # Get the CustomEmailAccount instance
        email_account = frappe.get_doc("Email Account", self.email_account.name)
        
        # Create a mock email object
        mock_email = MagicMock()
        mock_email.from_email = "support@example.com"
        
        # Patch the parent class send_auto_reply method
        with patch('frappe.email.doctype.email_account.email_account.EmailAccount.send_auto_reply') as mock_super:
            email_account.send_auto_reply(comm, mock_email)
            # Verify super was called exactly once
            mock_super.assert_called_once_with(comm, mock_email)

    def test_two_communications_skips_super(self):
        """Case 2: 2 Communications with same reference → super().send_auto_reply NOT called"""
        # Create a reference document (Issue)
        issue = frappe.get_doc({
            "doctype": "Issue",
            "subject": "Test Issue"
        }).insert()
        
        # Create first Communication
        comm1 = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "reference_doctype": "Issue",
            "reference_name": issue.name,
            "sender": "test1@example.com",
            "content": "First message"
        }).insert()
        
        # Create second Communication
        comm2 = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "reference_doctype": "Issue",
            "reference_name": issue.name,
            "sender": "test2@example.com",
            "content": "Second message"
        }).insert()
        
        # Get the CustomEmailAccount instance
        email_account = frappe.get_doc("Email Account", self.email_account.name)
        
        # Create a mock email object
        mock_email = MagicMock()
        mock_email.from_email = "support@example.com"
        
        # Patch the parent class send_auto_reply method
        with patch('frappe.email.doctype.email_account.email_account.EmailAccount.send_auto_reply') as mock_super:
            email_account.send_auto_reply(comm2, mock_email)
            # Verify super was NOT called
            mock_super.assert_not_called()

    def test_boundary_one_communication(self):
        """Boundary test: exactly 1 Communication (thread_count <= 1 is True)"""
        # Create a reference document
        issue = frappe.get_doc({
            "doctype": "Issue",
            "subject": "Boundary Test"
        }).insert()
        
        # Create exactly 1 Communication
        comm = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "reference_doctype": "Issue",
            "reference_name": issue.name,
            "sender": "test@example.com",
            "content": "Only message"
        }).insert()
        
        # Get the CustomEmailAccount instance
        email_account = frappe.get_doc("Email Account", self.email_account.name)
        
        # Create a mock email object
        mock_email = MagicMock()
        
        # Patch the parent class send_auto_reply method
        with patch('frappe.email.doctype.email_account.email_account.EmailAccount.send_auto_reply') as mock_super:
            email_account.send_auto_reply(comm, mock_email)
            # Should call super (thread_count = 1, which is <= 1)
            mock_super.assert_called_once()

    def test_boundary_two_communications(self):
        """Boundary test: exactly 2 Communications (thread_count <= 1 is False)"""
        # Create a reference document
        issue = frappe.get_doc({
            "doctype": "Issue",
            "subject": "Boundary Test 2"
        }).insert()
        
        # Create first Communication
        comm1 = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "reference_doctype": "Issue",
            "reference_name": issue.name,
            "sender": "test1@example.com",
            "content": "First"
        }).insert()
        
        # Create second Communication
        comm2 = frappe.get_doc({
            "doctype": "Communication",
            "communication_type": "Communication",
            "reference_doctype": "Issue",
            "reference_name": issue.name,
            "sender": "test2@example.com",
            "content": "Second"
        }).insert()
        
        # Get the CustomEmailAccount instance
        email_account = frappe.get_doc("Email Account", self.email_account.name)
        
        # Create a mock email object
        mock_email = MagicMock()
        
        # Patch the parent class send_auto_reply method
        with patch('frappe.email.doctype.email_account.email_account.EmailAccount.send_auto_reply') as mock_super:
            email_account.send_auto_reply(comm2, mock_email)
            # Should NOT call super (thread_count = 2, which is > 1)
            mock_super.assert_not_called()
