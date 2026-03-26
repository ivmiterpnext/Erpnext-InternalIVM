# Copyright (c) 2026, IVM and Contributors
# See license.txt

"""
Unit tests for ivm.ivm_integrations.sendgrid.inbound_parse.

All Frappe globals and external I/O are stubbed so these tests run without a
live Frappe/database environment (pure Python unittest).
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# _AttrDict — dict that also supports attribute-style access / assignment,
# mirroring frappe._dict / frappe.response behaviour.
# ---------------------------------------------------------------------------

class _AttrDict(dict):
    """A dict that also supports attribute-style access and assignment.

    Mirrors Frappe's ``frappe._dict`` / response object behaviour so that
    both ``frappe.response["http_status_code"]`` and
    ``frappe.response.http_status_code = 400`` work in tests.
    """

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key: str, value) -> None:
        self[key] = value

    def __delattr__(self, key: str) -> None:
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key) from None


# ---------------------------------------------------------------------------
# Minimal frappe stub — built once, installed unconditionally (MIN-1)
# ---------------------------------------------------------------------------

def _make_frappe_stub() -> types.ModuleType:
    """Return a minimal frappe module stub sufficient for the tests."""
    stub = types.ModuleType("frappe")

    # Exceptions that the production code references
    stub.PermissionError = PermissionError

    # Callables overridden per-test as needed
    stub.whitelist = lambda **kw: (lambda fn: fn)
    stub.enqueue = MagicMock()
    stub.get_doc = MagicMock()
    stub.log_error = MagicMock()
    stub.get_traceback = MagicMock(return_value="<traceback>")

    # frappe.response supports both dict-key and attribute access (frappe._dict)
    stub.response = _AttrDict()

    # frappe.request stub
    request_stub = MagicMock()
    request_stub.form = {}
    request_stub.headers = {}
    stub.request = request_stub

    # frappe.form_dict stub
    stub.form_dict = {}

    # frappe.conf stub
    stub.conf = {}

    # frappe.db stub — includes has_column for the idempotency guard
    db_stub = MagicMock()
    db_stub.get_value = MagicMock(return_value=None)
    db_stub.commit = MagicMock()
    db_stub.rollback = MagicMock()
    db_stub.has_column = MagicMock(return_value=False)  # safe default
    stub.db = db_stub

    # frappe.utils stub — includes is_valid_email for the from_email guard
    utils_stub = MagicMock()
    utils_stub.extract_email_id = MagicMock(
        side_effect=lambda addr: (
            addr.split("<")[-1].rstrip(">").strip() if "<" in addr else addr
        )
    )
    utils_stub.is_valid_email = MagicMock(return_value=True)  # accept by default
    stub.utils = utils_stub

    # frappe.logger stub
    logger_stub = MagicMock()
    stub.logger = MagicMock(return_value=logger_stub)

    return stub


# ---------------------------------------------------------------------------
# Build stubs for frappe.email.receive and frappe.utils.html_utils
# ---------------------------------------------------------------------------

_frappe_stub = _make_frappe_stub()

_email_receive_stub = types.ModuleType("frappe.email.receive")
_email_receive_stub.InboundMail = MagicMock()

_html_utils_stub = types.ModuleType("frappe.utils.html_utils")
# sanitize_html is a pass-through in tests — real sanitisation is a Frappe
# concern; we only verify it is *called* where required.
_html_utils_stub.sanitize_html = MagicMock(side_effect=lambda s: s)

# MIN-1: unconditional sys.modules assignment (not setdefault)
sys.modules["frappe"] = _frappe_stub
sys.modules["frappe.email"] = types.ModuleType("frappe.email")
sys.modules["frappe.email.receive"] = _email_receive_stub
sys.modules["frappe.utils"] = types.ModuleType("frappe.utils")
sys.modules["frappe.utils.html_utils"] = _html_utils_stub

# Now import the module under test (new location — MAJ-1)
from ivm.ivm_integrations.sendgrid import inbound_parse  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: fresh per-test frappe state
# ---------------------------------------------------------------------------

def _reset_frappe(
    *,
    secret: str | None = None,
    form: dict | None = None,
    headers: dict | None = None,
    db_get_value_side_effect=None,
) -> None:
    """Reset the frappe stub to sensible defaults before each test."""
    import frappe  # resolves to the stub

    frappe.response = _AttrDict()
    frappe.conf = {}
    if secret is not None:
        frappe.conf["sendgrid_inbound_secret"] = secret

    frappe.request.form = form or {}
    frappe.request.headers = headers or {}
    frappe.form_dict = {}

    frappe.enqueue.reset_mock()
    frappe.get_doc.reset_mock()
    frappe.log_error.reset_mock()
    frappe.db.get_value.reset_mock()
    frappe.db.commit.reset_mock()
    frappe.db.rollback.reset_mock()
    frappe.db.has_column.reset_mock()
    frappe.db.has_column.return_value = False  # safe default per test
    frappe.utils.is_valid_email.reset_mock()
    frappe.utils.is_valid_email.return_value = True  # accept all by default

    if db_get_value_side_effect is not None:
        frappe.db.get_value.side_effect = db_get_value_side_effect
    else:
        frappe.db.get_value.side_effect = None
        frappe.db.get_value.return_value = None

    _email_receive_stub.InboundMail.reset_mock()
    _html_utils_stub.sanitize_html.reset_mock()
    _html_utils_stub.sanitize_html.side_effect = lambda s: s  # pass-through


# ---------------------------------------------------------------------------
# Shared mail stub builder
# ---------------------------------------------------------------------------

def _make_mail_stub(
    *,
    subject: str | None = "Test Subject",
    from_email: str = "sender@example.com",
    text_content: str = "Plain body.",
    html_content: str | None = None,
    get_content_return: str | None = None,
    message_id: str | None = None,
) -> MagicMock:
    """Return a configured InboundMail MagicMock."""
    mail = MagicMock()
    mail.subject = subject
    mail.from_email = from_email
    mail.text_content = text_content
    mail.html_content = html_content or ""
    mail.content = html_content or text_content
    mail.get_content = MagicMock(return_value=get_content_return)
    mail.message_id = message_id
    return mail


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestReceiveEndpoint(unittest.TestCase):
    """Tests for the ``receive()`` webhook entry-point."""

    def test_missing_email_field_returns_400(self):
        """POST without 'email' field → HTTP 400 and an error payload."""
        _reset_frappe(form={})  # no 'email' key

        result = inbound_parse.receive()

        import frappe
        self.assertEqual(frappe.response.get("http_status_code"), 400)
        self.assertIn("error", result)
        frappe.enqueue.assert_not_called()

    def test_no_matching_email_account_returns_no_account(self):
        """When no Email Account matches, return {'status': 'no_account'} (HTTP 200)."""
        _reset_frappe(
            form={
                "email": "From: sender@example.com\r\nSubject: Hi\r\n\r\nBody",
                "to": "support@example.com",
            },
            db_get_value_side_effect=lambda *a, **kw: None,
        )

        result = inbound_parse.receive()

        self.assertEqual(result, {"status": "no_account"})
        import frappe
        frappe.enqueue.assert_not_called()
        frappe.log_error.assert_called_once()

    def test_valid_email_enqueues_job(self):
        """Valid POST with a matching Email Account → enqueues job, returns 'queued'."""
        raw = "From: sender@example.com\r\nSubject: Test\r\n\r\nHello"

        _reset_frappe(
            form={"email": raw, "to": "support@example.com"},
            db_get_value_side_effect=lambda *a, **kw: "Support Email Account",
        )

        result = inbound_parse.receive()

        self.assertEqual(result, {"status": "queued"})
        import frappe
        # Verify enqueue is called with the new module path (MAJ-1)
        frappe.enqueue.assert_called_once_with(
            "ivm.ivm_integrations.sendgrid.inbound_parse.process_inbound_email",
            queue="short",
            raw_email=raw,
            account_name="Support Email Account",
        )

    def test_invalid_secret_raises_permission_error(self):
        """Wrong shared secret → PermissionError raised before any processing."""
        _reset_frappe(
            secret="correct-secret",
            form={
                "email": "raw",
                "to": "support@example.com",
                "webhook_secret": "wrong-secret",
            },
        )

        with self.assertRaises(PermissionError):
            inbound_parse.receive()

        import frappe
        frappe.enqueue.assert_not_called()

    def test_valid_secret_in_header_is_accepted(self):
        """Correct secret in X-Webhook-Secret header allows the request through."""
        raw = "From: sender@example.com\r\nSubject: Hi\r\n\r\nBody"

        _reset_frappe(
            secret="my-secret",
            form={"email": raw, "to": "support@example.com"},
            headers={"X-Webhook-Secret": "my-secret"},
            db_get_value_side_effect=lambda *a, **kw: "Some Email Account",
        )

        result = inbound_parse.receive()
        self.assertEqual(result, {"status": "queued"})

    def test_no_secret_configured_skips_validation(self):
        """When sendgrid_inbound_secret is absent, any (or no) secret is accepted."""
        raw = "From: x@example.com\r\nSubject: Hi\r\n\r\n."

        _reset_frappe(
            form={"email": raw, "to": "support@example.com"},
            db_get_value_side_effect=lambda *a, **kw: "Default Email Account",
        )

        result = inbound_parse.receive()
        self.assertEqual(result, {"status": "queued"})

    def test_oversized_email_is_rejected(self):
        """Email larger than MAX_RAW_EMAIL_BYTES → 'rejected' status, no enqueue."""
        oversized = "x" * (inbound_parse.MAX_RAW_EMAIL_BYTES + 1)

        _reset_frappe(
            form={"email": oversized, "to": "support@example.com"},
            db_get_value_side_effect=lambda *a, **kw: "Some Email Account",
        )

        result = inbound_parse.receive()

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "payload_too_large")
        import frappe
        frappe.enqueue.assert_not_called()
        frappe.log_error.assert_called_once()

    def test_email_exactly_at_size_limit_is_accepted(self):
        """Email whose UTF-8 encoding equals exactly MAX_RAW_EMAIL_BYTES is allowed."""
        # Build a minimal valid-looking email that hits the limit exactly.
        # The size guard is strict (>), so == limit should pass.
        header = "From: a@b.com\r\nSubject: S\r\n\r\n"
        padding = "x" * (inbound_parse.MAX_RAW_EMAIL_BYTES - len(header.encode("utf-8")))
        at_limit = header + padding

        assert len(at_limit.encode("utf-8")) == inbound_parse.MAX_RAW_EMAIL_BYTES

        _reset_frappe(
            form={"email": at_limit, "to": "support@example.com"},
            db_get_value_side_effect=lambda *a, **kw: "Some Email Account",
        )

        result = inbound_parse.receive()
        self.assertEqual(result, {"status": "queued"})


# ---------------------------------------------------------------------------

class TestProcessInboundEmail(unittest.TestCase):
    """Tests for the ``process_inbound_email()`` background worker."""

    def test_process_inbound_email_creates_issue_with_correct_type(self):
        """Worker inserts an Issue with issue_type='Support' and correct fields.

        Also verifies (MIN-2) that the description field is populated, and
        confirms (MAJ-2) that frappe.db.commit() is NOT called by the worker.
        """
        _reset_frappe()
        import frappe

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            subject="Printer broken",
            from_email="user@customer.com",
            text_content="My printer is broken.",
            get_content_return=None,  # no HTML → plain text fallback
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0001"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email(
            raw_email="raw RFC 2822 bytes here",
            account_name="Support Email Account",
        )

        # Verify Issue was constructed with all mandatory fields
        second_call = frappe.get_doc.call_args_list[1]
        issue_dict: dict = second_call[0][0]

        self.assertEqual(issue_dict["doctype"], "Issue")
        self.assertEqual(issue_dict["issue_type"], "Support")
        self.assertEqual(issue_dict["raised_by"], "user@customer.com")
        self.assertEqual(issue_dict["subject"], "Printer broken")
        self.assertEqual(issue_dict["via_customer_portal"], 0)
        # MIN-2: description must be present and non-empty
        self.assertEqual(issue_dict["description"], "My printer is broken.")

        issue_stub.insert.assert_called_once_with(ignore_permissions=True)

        # MAJ-2: worker must NOT commit — the after_insert hook chain commits
        frappe.db.commit.assert_not_called()

    def test_process_inbound_email_uses_html_when_available(self):
        """Worker sets description to sanitized HTML when get_content() returns HTML."""
        _reset_frappe()
        import frappe

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            from_email="a@b.com",
            html_content="<p>Hello</p>",
            get_content_return="<p>Hello</p>",
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0002"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email("raw", "Test Account")

        second_call = frappe.get_doc.call_args_list[1]
        issue_dict = second_call[0][0]
        self.assertEqual(issue_dict["description"], "<p>Hello</p>")

        # CRIT-2: sanitize_html must have been called on the HTML content
        _html_utils_stub.sanitize_html.assert_called_once_with("<p>Hello</p>")

    def test_process_inbound_email_uses_plain_text_when_no_html(self):
        """Worker falls back to plain-text description when no HTML is present."""
        _reset_frappe()
        import frappe

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            from_email="a@b.com",
            text_content="Just plain text.",
            get_content_return=None,
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0003"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email("raw", "Test Account")

        second_call = frappe.get_doc.call_args_list[1]
        issue_dict = second_call[0][0]
        self.assertEqual(issue_dict["description"], "Just plain text.")

    def test_process_inbound_email_rolls_back_and_logs_on_error(self):
        """If Issue insertion raises, the worker rolls back and logs the error."""
        _reset_frappe()
        import frappe

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(from_email="x@y.com")
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.insert.side_effect = RuntimeError("DB exploded")
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        with self.assertRaises(RuntimeError):
            inbound_parse.process_inbound_email("raw", "Test Account")

        frappe.db.rollback.assert_called_once()
        frappe.log_error.assert_called_once()

    def test_missing_subject_falls_back_to_no_subject_sentinel(self):
        """MIN-3: mail.subject=None or '' → Issue subject is '(No Subject)'."""
        for empty_subject in (None, ""):
            with self.subTest(subject=empty_subject):
                _reset_frappe()
                import frappe

                email_account_doc = MagicMock()
                mail_stub = _make_mail_stub(
                    subject=empty_subject,
                    from_email="a@b.com",
                )
                _email_receive_stub.InboundMail.return_value = mail_stub

                issue_stub = MagicMock()
                issue_stub.name = "ISS-NOSUB"
                frappe.get_doc.side_effect = [email_account_doc, issue_stub]

                inbound_parse.process_inbound_email("raw", "Test Account")

                second_call = frappe.get_doc.call_args_list[1]
                issue_dict = second_call[0][0]
                self.assertEqual(issue_dict["subject"], "(No Subject)")

    def test_invalid_from_email_stored_as_empty_string(self):
        """MAJ-3: an invalid from_email is coerced to '' before being stored."""
        _reset_frappe()
        import frappe

        frappe.utils.is_valid_email.return_value = False  # simulate invalid address

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(from_email="not-an-email")
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0004"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email("raw", "Test Account")

        second_call = frappe.get_doc.call_args_list[1]
        issue_dict = second_call[0][0]
        self.assertEqual(issue_dict["raised_by"], "")

    def test_duplicate_message_id_is_skipped(self):
        """MAJ-4: if an Issue with the same Message-ID already exists, skip insert."""
        _reset_frappe()
        import frappe

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            from_email="a@b.com",
            message_id="<unique-id@example.com>",
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        # First db.get_value call (dedup lookup) returns an existing Issue name
        frappe.db.get_value.return_value = "ISS-EXISTING"

        frappe.get_doc.side_effect = [email_account_doc]

        inbound_parse.process_inbound_email("raw", "Test Account")

        # Only one get_doc call (Email Account); no Issue created
        self.assertEqual(frappe.get_doc.call_count, 1)
        frappe.db.commit.assert_not_called()

    def test_unique_message_id_proceeds_to_insert(self):
        """MAJ-4: if no duplicate exists, normal Issue creation proceeds."""
        _reset_frappe()
        import frappe

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            from_email="a@b.com",
            message_id="<new-unique-id@example.com>",
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        # Dedup lookup returns None → no existing Issue
        frappe.db.get_value.return_value = None

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0005"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email("raw", "Test Account")

        self.assertEqual(frappe.get_doc.call_count, 2)
        issue_stub.insert.assert_called_once_with(ignore_permissions=True)

    def test_message_id_stored_when_column_exists(self):
        """MAJ-4: custom_email_message_id is added to issue_data when column exists."""
        _reset_frappe()
        import frappe

        frappe.db.has_column.return_value = True  # column exists on this site
        frappe.db.get_value.return_value = None   # no duplicate

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            from_email="a@b.com",
            message_id="<store-me@example.com>",
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0006"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email("raw", "Test Account")

        second_call = frappe.get_doc.call_args_list[1]
        issue_dict = second_call[0][0]
        self.assertIn("custom_email_message_id", issue_dict)
        self.assertEqual(issue_dict["custom_email_message_id"], "<store-me@example.com>")

    def test_message_id_omitted_when_column_missing(self):
        """MAJ-4: custom_email_message_id is NOT added when column doesn't exist."""
        _reset_frappe()
        import frappe

        frappe.db.has_column.return_value = False  # column not migrated yet
        frappe.db.get_value.return_value = None

        email_account_doc = MagicMock()
        mail_stub = _make_mail_stub(
            from_email="a@b.com",
            message_id="<no-column@example.com>",
        )
        _email_receive_stub.InboundMail.return_value = mail_stub

        issue_stub = MagicMock()
        issue_stub.name = "ISS-0007"
        frappe.get_doc.side_effect = [email_account_doc, issue_stub]

        inbound_parse.process_inbound_email("raw", "Test Account")

        second_call = frappe.get_doc.call_args_list[1]
        issue_dict = second_call[0][0]
        self.assertNotIn("custom_email_message_id", issue_dict)


# ---------------------------------------------------------------------------

class TestValidateRequest(unittest.TestCase):
    """Tests for the internal ``_validate_request()`` helper."""

    def test_no_secret_in_conf_always_passes(self):
        """No secret configured → validation is a no-op."""
        _reset_frappe()  # frappe.conf has no sendgrid_inbound_secret
        inbound_parse._validate_request()  # must not raise

    def test_matching_secret_in_form_field_passes(self):
        """Correct secret in form field is accepted."""
        _reset_frappe(secret="abc123", form={"webhook_secret": "abc123"})
        import frappe
        frappe.form_dict = {"webhook_secret": "abc123"}
        inbound_parse._validate_request()  # must not raise

    def test_matching_secret_in_header_passes(self):
        """Correct secret in X-Webhook-Secret header is accepted."""
        _reset_frappe(secret="abc123", headers={"X-Webhook-Secret": "abc123"})
        inbound_parse._validate_request()  # must not raise

    def test_wrong_secret_raises_permission_error(self):
        """Mismatched secret always raises PermissionError."""
        _reset_frappe(secret="correct", form={"webhook_secret": "wrong"})
        import frappe
        frappe.form_dict = {"webhook_secret": "wrong"}
        with self.assertRaises(PermissionError):
            inbound_parse._validate_request()

    def test_missing_secret_raises_permission_error(self):
        """Secret configured but nothing provided → PermissionError."""
        _reset_frappe(secret="required", form={})
        import frappe
        frappe.form_dict = {}
        with self.assertRaises(PermissionError):
            inbound_parse._validate_request()

    def test_none_provided_when_secret_required_raises(self):
        """Explicit None for provided secret → PermissionError (not a crash)."""
        _reset_frappe(secret="required")
        import frappe
        frappe.request.headers = {}
        frappe.form_dict = {}
        with self.assertRaises(PermissionError):
            inbound_parse._validate_request()


if __name__ == "__main__":
    unittest.main()
