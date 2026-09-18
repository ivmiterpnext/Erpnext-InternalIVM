"""Integration tests for ivm.client_portal.utils.notifications"""

from unittest.mock import patch, MagicMock

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.utils.notifications import notify_assigned_rep


def _make_contact(first_name, user=None):
    return frappe.get_doc({
        "doctype": "Contact",
        "first_name": first_name,
        "user": user,
    }).insert(ignore_permissions=True)


def _make_submitted_quote(signer_contacts, sales_representative="Administrator"):
    """Create and submit a Service Quote with the given signer contacts.

    Mocks out the on_submit event handler (which provisions portal users and
    sets status to Sent) and manually sets the required post-submit state.

    Returns (quote_doc, [signer_row_name, ...]).
    """
    top_contact = _make_contact(f"TopSR-{frappe.generate_hash(length=6)}")
    signers = [{"contact": c.name, "status": "Pending"} for c in signer_contacts]
    doc = frappe.get_doc({
        "doctype": "Service Quote",
        "contact": top_contact.name,
        "sales_representative": sales_representative,
        "customer": "_Test Customer",
        "signers": signers,
    })
    doc.insert(ignore_permissions=True)

    with patch("ivm.client_portal.event_handlers.service_quote.on_submit"):
        doc.submit()

    frappe.db.set_value("Service Quote", doc.name, "status", "Sent")
    doc.reload()
    return doc, [r.name for r in doc.signers]


@patch("ivm.client_portal.utils.notifications.frappe.sendmail")
class TestNotifyAssignedRep(ERPNextTestSuite):
    """notify_assigned_rep"""

    def test_signer_row_not_found_no_email_sent(self, mock_sendmail):
        """If signer_row_name doesn't match any row, sendmail not called."""
        signer_contact = _make_contact("SR NotFound")
        quote, signer_names = _make_submitted_quote([signer_contact])

        notify_assigned_rep(quote.name, "nonexistent-row-name", "Accepted")

        mock_sendmail.assert_not_called()

    def test_signer_accepted_name_used_in_message(self, mock_sendmail):
        """Signer's accepted_name appears in email message body."""
        signer_contact = _make_contact("SR AcceptedName")
        quote, signer_names = _make_submitted_quote([signer_contact])

        # Set accepted_name on the signer row
        frappe.db.set_value(
            "Service Quote Signer",
            signer_names[0],
            "accepted_name",
            "John Doe",
        )

        notify_assigned_rep(quote.name, signer_names[0], "Accepted")

        mock_sendmail.assert_called_once()
        message = mock_sendmail.call_args.kwargs["message"]
        self.assertIn("John Doe", message)

    def test_contact_first_name_used_when_accepted_name_empty(self, mock_sendmail):
        """Contact's first_name used if signer's accepted_name is empty."""
        signer_contact = _make_contact("ContactFirstName")
        quote, signer_names = _make_submitted_quote([signer_contact])

        # Ensure accepted_name is empty (default)
        frappe.db.set_value(
            "Service Quote Signer",
            signer_names[0],
            "accepted_name",
            "",
        )

        notify_assigned_rep(quote.name, signer_names[0], "Accepted")

        mock_sendmail.assert_called_once()
        message = mock_sendmail.call_args.kwargs["message"]
        self.assertIn("ContactFirstName", message)

    def test_unknown_fallback_when_no_names_available(self, mock_sendmail):
        """Falls back to 'Unknown' if accepted_name and contact first_name both empty."""
        # Create contact with no first_name
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": "",
        }).insert(ignore_permissions=True)

        quote, signer_names = _make_submitted_quote([contact])

        # Ensure accepted_name is empty
        frappe.db.set_value(
            "Service Quote Signer",
            signer_names[0],
            "accepted_name",
            "",
        )

        notify_assigned_rep(quote.name, signer_names[0], "Accepted")

        mock_sendmail.assert_called_once()
        message = mock_sendmail.call_args.kwargs["message"]
        self.assertIn("Unknown", message)

    def test_no_email_sent_if_rep_has_no_email(self, mock_sendmail):
        """If sales_representative User has no email, sendmail not called."""
        # Create a User with no email
        rep_user = frappe.get_doc({
            "doctype": "User",
            "email": f"norep-{frappe.generate_hash(length=6)}@test.local",
            "first_name": "NoEmailRep",
            "user_type": "System User",
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True)

        # Clear the email field
        frappe.db.set_value("User", rep_user.email, "email", "")

        signer_contact = _make_contact("SR NoRepEmail")
        quote, signer_names = _make_submitted_quote(
            [signer_contact],
            sales_representative=rep_user.email,
        )

        notify_assigned_rep(quote.name, signer_names[0], "Accepted")

        mock_sendmail.assert_not_called()

    def test_reason_included_in_message_when_provided(self, mock_sendmail):
        """Reason block included in message body when reason provided."""
        signer_contact = _make_contact("SR Reason")
        quote, signer_names = _make_submitted_quote([signer_contact])

        notify_assigned_rep(
            quote.name,
            signer_names[0],
            "Declined",
            reason="Too expensive for our budget",
        )

        mock_sendmail.assert_called_once()
        message = mock_sendmail.call_args.kwargs["message"]
        self.assertIn("Reason provided:", message)
        self.assertIn("Too expensive for our budget", message)

    def test_reason_html_escaped_in_message(self, mock_sendmail):
        """Reason is HTML-escaped; raw tags don't appear unescaped."""
        signer_contact = _make_contact("SR HTMLEscape")
        quote, signer_names = _make_submitted_quote([signer_contact])

        malicious_reason = "<script>alert('xss')</script>"
        notify_assigned_rep(
            quote.name,
            signer_names[0],
            "Declined",
            reason=malicious_reason,
        )

        mock_sendmail.assert_called_once()
        message = mock_sendmail.call_args.kwargs["message"]

        # Raw script tag should NOT appear
        self.assertNotIn("<script>", message)
        # Escaped form should appear
        self.assertIn("&lt;script&gt;", message)

    def test_no_reason_block_when_reason_omitted(self, mock_sendmail):
        """No reason block in message when reason is None."""
        signer_contact = _make_contact("SR NoReason")
        quote, signer_names = _make_submitted_quote([signer_contact])

        notify_assigned_rep(quote.name, signer_names[0], "Declined", reason=None)

        mock_sendmail.assert_called_once()
        message = mock_sendmail.call_args.kwargs["message"]
        self.assertNotIn("Reason provided:", message)

    @patch("ivm.client_portal.utils.notifications.frappe.log_error")
    def test_exception_logged_with_quote_name(self, mock_log_error, mock_sendmail):
        """Exception caught and logged with quote name; no exception propagates."""
        signer_contact = _make_contact("SR Exception")
        quote, signer_names = _make_submitted_quote([signer_contact])

        # Mock frappe.get_doc to raise an exception
        with patch("ivm.client_portal.utils.notifications.frappe.get_doc") as mock_get_doc:
            mock_get_doc.side_effect = ValueError("Simulated error")

            # Should not raise
            notify_assigned_rep(quote.name, signer_names[0], "Accepted")

        # log_error should have been called
        mock_log_error.assert_called_once()
        logged_message = mock_log_error.call_args[0][0]
        # Quote name should appear in the logged message
        self.assertIn(quote.name, logged_message)

        # sendmail should not have been called
        mock_sendmail.assert_not_called()
