"""Tests for ivm.integrations.hubspot.activity_handler"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.activity_handler import (
	_as_owner,
	_create_calendar_note,
	_normalize_email_list,
	_parse_timestamp,
	_strip_quoted_reply,
	_sync_attachments,
	_sync_call,
	_sync_email,
	_sync_meeting,
	_sync_note,
	_sync_task,
	_truncate,
	handle_engagement_webhook,
)
from ivm.integrations.hubspot.constants import (
	CALL_DIRECTION_MAP,
	CALL_STATUS_MAP,
	ENGAGEMENT_TYPE_CALLS,
	ENGAGEMENT_TYPE_EMAILS,
	ENGAGEMENT_TYPE_MEETINGS,
	ENGAGEMENT_TYPE_NOTES,
	ENGAGEMENT_TYPE_TASKS,
	HUBSPOT_ENGAGEMENT_ID_FIELD,
	TASK_PRIORITY_MAP,
	TASK_STATUS_MAP,
)


class TestNormalizeEmailList(FrappeTestCase):
	"""_normalize_email_list utility function"""

	def test_semicolon_separated_list(self):
		result = _normalize_email_list("foo@bar.com; baz@qux.com")
		self.assertEqual(result, "foo@bar.com, baz@qux.com")

	def test_comma_separated_list(self):
		result = _normalize_email_list("foo@bar.com, baz@qux.com")
		self.assertEqual(result, "foo@bar.com, baz@qux.com")

	def test_mixed_separators(self):
		result = _normalize_email_list("foo@bar.com; baz@qux.com , hello@world.com")
		self.assertEqual(result, "foo@bar.com, baz@qux.com, hello@world.com")

	def test_whitespace_trimmed(self):
		result = _normalize_email_list("  foo@bar.com  ;  baz@qux.com  ")
		self.assertEqual(result, "foo@bar.com, baz@qux.com")

	def test_empty_string(self):
		result = _normalize_email_list("")
		self.assertEqual(result, "")

	def test_none_value(self):
		result = _normalize_email_list(None)
		self.assertEqual(result, "")


class TestParseTimestamp(FrappeTestCase):
	"""_parse_timestamp utility function"""

	def test_epoch_milliseconds_string(self):
		epoch_ms = "1717427120000"  # 2024-06-03T16:45:20Z
		result = _parse_timestamp(epoch_ms)
		self.assertIsNotNone(result)
		self.assertIn("2024-06-03", result)

	def test_iso8601_with_z_suffix(self):
		iso_str = "2026-06-03T16:45:20.000Z"
		result = _parse_timestamp(iso_str)
		self.assertIsNotNone(result)
		self.assertIn("2026-06-03", result)

	def test_iso8601_with_plus_offset(self):
		iso_str = "2026-06-03T16:45:20.000+00:00"
		result = _parse_timestamp(iso_str)
		self.assertIsNotNone(result)
		self.assertIn("2026-06-03", result)

	def test_garbage_input_returns_none(self):
		result = _parse_timestamp("not a timestamp")
		self.assertIsNone(result)

	def test_empty_string_returns_none(self):
		result = _parse_timestamp("")
		self.assertIsNone(result)

	def test_none_input_returns_none(self):
		result = _parse_timestamp(None)
		self.assertIsNone(result)


class TestTruncate(FrappeTestCase):
	"""_truncate utility function"""

	def test_text_within_limit(self):
		text = "Short text"
		result = _truncate(text, 50)
		self.assertEqual(result, "Short text")

	def test_text_exceeds_limit(self):
		text = "This is a very long text that exceeds the maximum length"
		result = _truncate(text, 20)
		self.assertEqual(len(result), 20)
		self.assertTrue(result.endswith("…"))

	def test_html_tags_stripped(self):
		text = "<p>Hello <b>world</b></p>"
		result = _truncate(text, 50)
		self.assertEqual(result, "Hello world")

	def test_html_tags_stripped_and_truncated(self):
		text = "<p>This is a very long text with <b>HTML tags</b> that needs truncation</p>"
		result = _truncate(text, 20)
		self.assertEqual(len(result), 20)
		self.assertTrue(result.endswith("…"))


class TestStripQuotedReply(FrappeTestCase):
	"""_strip_quoted_reply utility function"""

	def test_outlook_html_quote_stripped(self):
		content = '<p>My reply here</p><div style="border-top: solid 1px #ccc"><p>Original message</p></div>'
		result = _strip_quoted_reply(content, is_html=True)
		self.assertIn("My reply here", result)
		self.assertNotIn("Original message", result)

	def test_gmail_html_quote_stripped(self):
		content = '<p>My reply</p><blockquote class="gmail_quote"><p>Quoted text</p></blockquote>'
		result = _strip_quoted_reply(content, is_html=True)
		self.assertIn("My reply", result)
		self.assertNotIn("Quoted text", result)

	def test_plain_text_quote_stripped(self):
		content = "My reply\n\nOn Mon, Jan 1 wrote:\n> Original message"
		result = _strip_quoted_reply(content, is_html=False)
		self.assertIn("My reply", result)
		self.assertNotIn("Original message", result)

	def test_plain_text_with_quote_markers(self):
		content = "My reply\n> Quoted line 1\n> Quoted line 2"
		result = _strip_quoted_reply(content, is_html=False)
		self.assertIn("My reply", result)
		self.assertNotIn("> Quoted", result)

	def test_no_quote_returns_original(self):
		content = "Just a simple message"
		result = _strip_quoted_reply(content, is_html=False)
		self.assertEqual(result, content)

	def test_empty_content(self):
		result = _strip_quoted_reply("", is_html=False)
		self.assertEqual(result, "")


class TestAsOwner(FrappeTestCase):
	"""_as_owner context manager"""

	@patch("ivm.integrations.hubspot.activity_handler.api.get_owner_email")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.exists")
	def test_yields_email_when_user_exists(self, mock_exists, mock_get_email):
		mock_get_email.return_value = "owner@example.com"
		mock_exists.return_value = True

		with _as_owner("hubspot_owner_123") as email:
			self.assertEqual(email, "owner@example.com")

	@patch("ivm.integrations.hubspot.activity_handler.api.get_owner_email")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.exists")
	def test_yields_none_when_user_not_found(self, mock_exists, mock_get_email):
		mock_get_email.return_value = "owner@example.com"
		mock_exists.return_value = False

		with _as_owner("hubspot_owner_123") as email:
			self.assertIsNone(email)

	@patch("ivm.integrations.hubspot.activity_handler.api.get_owner_email")
	def test_yields_none_when_no_owner_id(self, mock_get_email):
		with _as_owner(None) as email:
			self.assertIsNone(email)
			mock_get_email.assert_not_called()


class TestSyncNote(FrappeTestCase):
	"""_sync_note function"""

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	def test_creates_new_note_with_body(
		self, mock_as_owner, mock_new_doc, mock_get_existing, mock_sync_attach
	):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)

		mock_doc = MagicMock()
		mock_doc.name = "FCRM-Note-001"
		mock_doc.doctype = "FCRM Note"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_note_body": "Test note content",
			"hs_attachment_ids": "file1;file2",
			"hubspot_owner_id": "owner_123",
		}

		_sync_note("eng_123", props, "Deal-001")

		mock_new_doc.assert_called_once_with("FCRM Note")
		self.assertEqual(mock_doc.content, "Test note content")
		self.assertEqual(mock_doc.reference_doctype, "CRM Deal")
		self.assertEqual(mock_doc.reference_docname, "Deal-001")
		mock_doc.insert.assert_called_once()
		mock_sync_attach.assert_called_once_with("file1;file2", "Deal-001")

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.get_doc")
	def test_updates_existing_note(self, mock_get_doc, mock_get_existing, mock_sync_attach):
		mock_get_existing.return_value = "FCRM-Note-001"
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		props = {
			"hs_note_body": "Updated content",
			"hs_attachment_ids": "file1",
		}

		_sync_note("eng_123", props, "Deal-001")

		mock_get_doc.assert_called_once_with("FCRM Note", "FCRM-Note-001")
		self.assertEqual(mock_doc.content, "Updated content")
		mock_doc.save.assert_called_once()
		mock_sync_attach.assert_called_once_with("file1", "Deal-001")

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_skips_empty_note_but_syncs_attachments(self, mock_get_existing, mock_sync_attach):
		mock_get_existing.return_value = None

		props = {
			"hs_note_body": "",
			"hs_attachment_ids": "file1;file2",
		}

		_sync_note("eng_123", props, "Deal-001")

		mock_sync_attach.assert_called_once_with("file1;file2", "Deal-001")

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_skips_attachment_only_note_when_no_attachments(self, mock_get_existing, mock_sync_attach):
		mock_get_existing.return_value = None

		props = {
			"hs_note_body": "",
			"hs_attachment_ids": "",
		}

		_sync_note("eng_123", props, "Deal-001")

		mock_sync_attach.assert_not_called()


class TestSyncCall(FrappeTestCase):
	"""_sync_call function"""

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._parse_timestamp")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_creates_inbound_call(
		self, mock_get_existing, mock_new_doc, mock_as_owner, mock_parse_ts, mock_sync_attach
	):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)
		mock_parse_ts.return_value = "2026-06-03 16:45:20"

		mock_doc = MagicMock()
		mock_doc.name = "CRM-Call-001"
		mock_doc.doctype = "CRM Call Log"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_call_direction": "INBOUND",
			"hs_call_status": "COMPLETED",
			"hs_call_from_number": "+1234567890",
			"hs_call_to_number": "+0987654321",
			"hs_call_duration": "120000",
			"hs_timestamp": "1717427120000",
			"hubspot_owner_id": "owner_123",
		}

		_sync_call("eng_123", props, "Deal-001")

		mock_new_doc.assert_called_once_with("CRM Call Log")
		self.assertEqual(mock_doc.type, "Incoming")
		self.assertEqual(mock_doc.duration, 120)
		self.assertEqual(mock_doc.receiver, "owner@example.com")
		mock_doc.insert.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._parse_timestamp")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_creates_outbound_call(
		self, mock_get_existing, mock_new_doc, mock_as_owner, mock_parse_ts, mock_sync_attach
	):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)
		mock_parse_ts.return_value = "2026-06-03 16:45:20"

		mock_doc = MagicMock()
		mock_doc.name = "CRM-Call-002"
		mock_doc.doctype = "CRM Call Log"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_call_direction": "OUTBOUND",
			"hs_call_status": "COMPLETED",
			"hs_call_from_number": "+1234567890",
			"hs_call_to_number": "+0987654321",
			"hs_call_duration": "120000",
			"hs_timestamp": "1717427120000",
			"hubspot_owner_id": "owner_123",
		}

		_sync_call("eng_123", props, "Deal-001")

		self.assertEqual(mock_doc.type, "Outgoing")
		self.assertEqual(mock_doc.caller, "owner@example.com")

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._parse_timestamp")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_duration_invalid_defaults_to_zero(
		self, mock_get_existing, mock_new_doc, mock_as_owner, mock_parse_ts, mock_sync_attach
	):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value=None)
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)
		mock_parse_ts.return_value = "2026-06-03 16:45:20"

		mock_doc = MagicMock()
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_call_direction": "OUTBOUND",
			"hs_call_status": "COMPLETED",
			"hs_call_from_number": "+1234567890",
			"hs_call_to_number": "+0987654321",
			"hs_call_duration": "not_a_number",
			"hs_timestamp": "1717427120000",
		}

		_sync_call("eng_123", props, "Deal-001")

		self.assertEqual(mock_doc.duration, 0)

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.get_doc")
	def test_updates_existing_call(self, mock_get_doc, mock_get_existing, mock_sync_attach):
		mock_get_existing.return_value = "CRM-Call-001"
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		props = {
			"hs_call_status": "COMPLETED",
			"hs_call_recording_url": "https://example.com/recording.mp3",
			"hs_attachment_ids": "file1",
		}

		_sync_call("eng_123", props, "Deal-001")

		mock_get_doc.assert_called_once_with("CRM Call Log", "CRM-Call-001")
		self.assertEqual(mock_doc.status, "Completed")
		self.assertEqual(mock_doc.recording_url, "https://example.com/recording.mp3")
		mock_doc.save.assert_called_once()


class TestSyncEmail(FrappeTestCase):
	"""_sync_email function"""

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._parse_timestamp")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.exists")
	def test_creates_inbound_email(
		self, mock_exists, mock_new_doc, mock_as_owner, mock_parse_ts, mock_sync_attach
	):
		mock_exists.return_value = False
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)
		mock_parse_ts.return_value = "2026-06-03 16:45:20"

		mock_doc = MagicMock()
		mock_doc.name = "Comm-001"
		mock_doc.doctype = "Communication"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_email_subject": "Test Subject",
			"hs_email_direction": "INCOMING_EMAIL",
			"hs_email_status": "RECEIVED",
			"hs_email_from_email": "sender@example.com",
			"hs_email_to_email": "recipient@example.com",
			"hs_email_cc_email": "cc@example.com",
			"hs_email_bcc_email": "bcc@example.com",
			"hs_email_html": "<p>Email body</p>",
			"hs_timestamp": "1717427120000",
			"hubspot_owner_id": "owner_123",
		}

		_sync_email("eng_123", props, "Deal-001")

		mock_new_doc.assert_called_once_with("Communication")
		self.assertEqual(mock_doc.subject, "Test Subject")
		self.assertEqual(mock_doc.sent_or_received, "Received")
		self.assertEqual(mock_doc.sender, "sender@example.com")
		mock_doc.insert.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.exists")
	def test_skips_duplicate_email_but_syncs_attachments(self, mock_exists, mock_sync_attach):
		mock_exists.return_value = True

		props = {
			"hs_email_subject": "Test Subject",
			"hs_attachment_ids": "file1;file2",
		}

		_sync_email("eng_123", props, "Deal-001")

		mock_sync_attach.assert_called_once_with("file1;file2", "Deal-001")

	@patch("ivm.integrations.hubspot.activity_handler._create_calendar_note")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.exists")
	def test_routes_calendar_response_to_calendar_note(self, mock_exists, mock_create_cal):
		props = {
			"hs_email_subject": "Accepted: Team Meeting",
		}

		_sync_email("eng_123", props, "Deal-001")

		mock_create_cal.assert_called_once_with("eng_123", props, "Deal-001")
		mock_exists.assert_not_called()


class TestSyncTask(FrappeTestCase):
	"""_sync_task function"""

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_creates_new_task(self, mock_get_existing, mock_new_doc, mock_as_owner, mock_sync_attach):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)

		mock_doc = MagicMock()
		mock_doc.name = "CRM-Task-001"
		mock_doc.doctype = "CRM Task"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_task_subject": "Follow up with client",
			"hs_task_body": "Call them tomorrow",
			"hs_task_status": "NOT_STARTED",
			"hs_task_priority": "HIGH",
			"hubspot_owner_id": "owner_123",
			"hs_attachment_ids": "file1",
		}

		_sync_task("eng_123", props, "Deal-001")

		mock_new_doc.assert_called_once_with("CRM Task")
		self.assertEqual(mock_doc.title, "Follow up with client")
		self.assertEqual(mock_doc.description, "Call them tomorrow")
		self.assertEqual(mock_doc.status, "Todo")
		self.assertEqual(mock_doc.priority, "High")
		self.assertEqual(mock_doc.assigned_to, "owner@example.com")
		mock_doc.insert.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.get_doc")
	def test_updates_existing_task(self, mock_get_doc, mock_get_existing, mock_sync_attach):
		mock_get_existing.return_value = "CRM-Task-001"
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		props = {
			"hs_task_subject": "Updated task",
			"hs_task_body": "Updated description",
			"hs_task_status": "IN_PROGRESS",
			"hs_task_priority": "MEDIUM",
			"hs_attachment_ids": "file1",
		}

		_sync_task("eng_123", props, "Deal-001")

		mock_get_doc.assert_called_once_with("CRM Task", "CRM-Task-001")
		self.assertEqual(mock_doc.title, "Updated task")
		self.assertEqual(mock_doc.status, "In Progress")
		self.assertEqual(mock_doc.priority, "Medium")
		mock_doc.save.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_unknown_status_defaults_to_todo(
		self, mock_get_existing, mock_new_doc, mock_as_owner, mock_sync_attach
	):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value=None)
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)

		mock_doc = MagicMock()
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_task_subject": "Task",
			"hs_task_body": "",
			"hs_task_status": "UNKNOWN_STATUS",
			"hs_task_priority": "UNKNOWN_PRIORITY",
		}

		_sync_task("eng_123", props, "Deal-001")

		self.assertEqual(mock_doc.status, "Todo")
		self.assertEqual(mock_doc.priority, "Medium")


class TestSyncMeeting(FrappeTestCase):
	"""_sync_meeting function"""

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._parse_timestamp")
	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_creates_new_meeting_note(
		self, mock_get_existing, mock_new_doc, mock_as_owner, mock_parse_ts, mock_sync_attach
	):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)
		mock_parse_ts.side_effect = ["2026-06-03 10:00:00", "2026-06-03 11:00:00"]

		mock_doc = MagicMock()
		mock_doc.name = "FCRM-Note-001"
		mock_doc.doctype = "FCRM Note"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_meeting_title": "Client Sync",
			"hs_meeting_body": "Discuss project status",
			"hs_meeting_start_time": "1717427120000",
			"hs_meeting_end_time": "1717430720000",
			"hubspot_owner_id": "owner_123",
			"hs_attachment_ids": "file1",
		}

		_sync_meeting("eng_123", props, "Deal-001")

		mock_new_doc.assert_called_once_with("FCRM Note")
		self.assertIn("[Meeting]", mock_doc.title)
		self.assertIn("Client Sync", mock_doc.title)
		self.assertIn("Start:", mock_doc.content)
		self.assertIn("End:", mock_doc.content)
		self.assertIn("Discuss project status", mock_doc.content)
		mock_doc.insert.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler._sync_attachments")
	@patch("ivm.integrations.hubspot.activity_handler._parse_timestamp")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.get_doc")
	def test_updates_existing_meeting(self, mock_get_doc, mock_get_existing, mock_parse_ts, mock_sync_attach):
		mock_get_existing.return_value = "FCRM-Note-001"
		mock_parse_ts.side_effect = ["2026-06-03 10:00:00", "2026-06-03 11:00:00"]
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		props = {
			"hs_meeting_title": "Updated Meeting",
			"hs_meeting_body": "Updated body",
			"hs_meeting_start_time": "1717427120000",
			"hs_meeting_end_time": "1717430720000",
			"hs_attachment_ids": "file1",
		}

		_sync_meeting("eng_123", props, "Deal-001")

		mock_get_doc.assert_called_once_with("FCRM Note", "FCRM-Note-001")
		self.assertIn("[Meeting]", mock_doc.title)
		self.assertIn("Updated Meeting", mock_doc.title)
		mock_doc.save.assert_called_once()


class TestCreateCalendarNote(FrappeTestCase):
	"""_create_calendar_note function"""

	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_creates_accepted_calendar_note(self, mock_get_existing, mock_new_doc, mock_as_owner):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value="owner@example.com")
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)

		mock_doc = MagicMock()
		mock_doc.name = "FCRM-Note-001"
		mock_doc.doctype = "FCRM Note"
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_email_subject": "Accepted: Team Standup",
			"hs_email_from_email": "contact@example.com",
			"hubspot_owner_id": "owner_123",
		}

		_create_calendar_note("eng_123", props, "Deal-001")

		mock_new_doc.assert_called_once_with("FCRM Note")
		self.assertIn("[Meeting Accepted]", mock_doc.title)
		self.assertIn("Team Standup", mock_doc.title)
		self.assertIn("accepted", mock_doc.content)
		mock_doc.insert.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler._as_owner")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_creates_declined_calendar_note(self, mock_get_existing, mock_new_doc, mock_as_owner):
		mock_get_existing.return_value = None
		mock_as_owner.return_value.__enter__ = Mock(return_value=None)
		mock_as_owner.return_value.__exit__ = Mock(return_value=False)

		mock_doc = MagicMock()
		mock_new_doc.return_value = mock_doc

		props = {
			"hs_email_subject": "Declined: Team Standup",
			"hs_email_from_email": "contact@example.com",
		}

		_create_calendar_note("eng_123", props, "Deal-001")

		self.assertIn("[Meeting Declined]", mock_doc.title)
		self.assertIn("declined", mock_doc.content)

	@patch("ivm.integrations.hubspot.activity_handler._get_existing")
	def test_skips_if_already_exists(self, mock_get_existing):
		mock_get_existing.return_value = "FCRM-Note-001"

		props = {
			"hs_email_subject": "Accepted: Meeting",
		}

		_create_calendar_note("eng_123", props, "Deal-001")

		# Should return early without creating anything


class TestSyncAttachments(FrappeTestCase):
	"""_sync_attachments function"""

	@patch("ivm.integrations.hubspot.activity_handler.api.download_file")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.new_doc")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	def test_downloads_and_creates_new_file(self, mock_get_value, mock_new_doc, mock_download):
		mock_get_value.return_value = None
		mock_download.return_value = ("document.pdf", b"PDF content")

		mock_doc = MagicMock()
		mock_new_doc.return_value = mock_doc

		_sync_attachments("file_123", "Deal-001")

		mock_new_doc.assert_called_once_with("File")
		self.assertIn("hs_file_123_", mock_doc.file_name)
		self.assertEqual(mock_doc.attached_to_doctype, "CRM Deal")
		self.assertEqual(mock_doc.attached_to_name, "Deal-001")
		mock_doc.save.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	def test_skips_already_synced_file(self, mock_get_value):
		mock_get_value.return_value = "File-001"

		_sync_attachments("file_123", "Deal-001")

		# Should return early without downloading

	@patch("ivm.integrations.hubspot.activity_handler.api.download_file")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	def test_continues_on_download_failure(self, mock_get_value, mock_download):
		mock_get_value.return_value = None
		mock_download.return_value = None

		_sync_attachments("file_123;file_456", "Deal-001")

		# Should continue processing remaining files without raising

	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	def test_skips_empty_attachment_ids(self, mock_get_value):
		_sync_attachments("", "Deal-001")
		_sync_attachments(None, "Deal-001")

		mock_get_value.assert_not_called()


class TestHandleEngagementWebhook(FrappeTestCase):
	"""handle_engagement_webhook function"""

	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement")
	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement_deal_ids")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	@patch("ivm.integrations.hubspot.sync_utils.set_acting_user")
	def test_syncs_engagement_to_existing_deal(
		self, mock_set_user, mock_get_value, mock_get_deal_ids, mock_get_eng
	):
		mock_get_deal_ids.return_value = ["deal_123"]
		mock_get_value.return_value = "Deal-001"
		mock_get_eng.return_value = {"properties": {"hs_note_body": "Test note"}}

		mock_handler = MagicMock()
		with patch("ivm.integrations.hubspot.activity_handler.frappe.db.set_value"):
			with patch.dict(
				"ivm.integrations.hubspot.activity_handler._TYPE_HANDLERS",
				{ENGAGEMENT_TYPE_NOTES: mock_handler},
			):
				handle_engagement_webhook(ENGAGEMENT_TYPE_NOTES, "eng_123")

		mock_handler.assert_called_once()

	@patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists")
	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement")
	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement_deal_ids")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	@patch("ivm.integrations.hubspot.sync_utils.set_acting_user")
	def test_creates_deal_if_missing(
		self, mock_set_user, mock_get_value, mock_get_deal_ids, mock_get_eng, mock_ensure_deal
	):
		mock_get_deal_ids.return_value = ["deal_123"]
		mock_get_value.return_value = None
		mock_ensure_deal.return_value = ("Deal-001", {})
		mock_get_eng.return_value = {"properties": {"hs_note_body": "Test note"}}

		mock_handler = MagicMock()
		with patch("ivm.integrations.hubspot.activity_handler.frappe.db.set_value"):
			with patch.dict(
				"ivm.integrations.hubspot.activity_handler._TYPE_HANDLERS",
				{ENGAGEMENT_TYPE_NOTES: mock_handler},
			):
				handle_engagement_webhook(ENGAGEMENT_TYPE_NOTES, "eng_123")

		mock_ensure_deal.assert_called_once()
		mock_handler.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler.frappe.enqueue")
	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement_deal_ids")
	@patch("ivm.integrations.hubspot.sync_utils.set_acting_user")
	def test_re_enqueues_on_rate_limit(self, mock_set_user, mock_get_deal_ids, mock_enqueue):
		from ivm.integrations.hubspot import api

		mock_get_deal_ids.side_effect = api.HubSpotRateLimitExhausted(60)

		with patch("ivm.integrations.hubspot.activity_handler.frappe.logger"):
			handle_engagement_webhook(ENGAGEMENT_TYPE_NOTES, "eng_123")

		mock_enqueue.assert_called_once()

	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement_deal_ids")
	@patch("ivm.integrations.hubspot.sync_utils.set_acting_user")
	def test_returns_when_no_deal_associated(self, mock_set_user, mock_get_deal_ids):
		mock_get_deal_ids.return_value = []

		with patch("ivm.integrations.hubspot.activity_handler.frappe.logger"):
			handle_engagement_webhook(ENGAGEMENT_TYPE_NOTES, "eng_123")

		# Should return early without further processing

	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement")
	@patch("ivm.integrations.hubspot.activity_handler.api.get_engagement_deal_ids")
	@patch("ivm.integrations.hubspot.activity_handler.frappe.db.get_value")
	@patch("ivm.integrations.hubspot.sync_utils.set_acting_user")
	def test_logs_warning_for_unknown_engagement_type(
		self, mock_set_user, mock_get_value, mock_get_deal_ids, mock_get_eng
	):
		mock_get_deal_ids.return_value = ["deal_123"]
		mock_get_value.return_value = "Deal-001"
		mock_get_eng.return_value = {"properties": {}}

		with patch("ivm.integrations.hubspot.activity_handler.frappe.logger"):
			handle_engagement_webhook("unknown_type", "eng_123")

		# Should log warning and return
