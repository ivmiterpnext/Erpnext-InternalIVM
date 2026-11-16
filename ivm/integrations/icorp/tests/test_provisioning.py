"""Tests for ivm.integrations.icorp.provisioning (contact phone, error text, payloads).

iCorp is mocked at icorp_api_post. Error logging is patched out so no Error Log rows
are written here (the persistence behavior is covered in the doctype tests).
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.icorp.provisioning import (
	_ERROR_TEXT_MAX_CHARS,
	build_contact_payload,
	create_icorp_client_with_error,
	create_icorp_contact_with_error,
	get_contact_phone,
	icorp_error_text,
)

_ICORP_POST = "ivm.integrations.icorp.provisioning.icorp_api_post"
_LOG_ERROR = "ivm.integrations.icorp.provisioning.log_icorp_error"
_NON_JSON_ERROR = {
	"error": "Invalid JSON response",
	"status_code": 400,
	"text": "Must have a least 1 contact phone number.",
}


def _contact(**fields):
	"""Unsaved Contact doc; provisioning only reads attributes via .get / attribute access."""
	return frappe.get_doc({"doctype": "Contact", "first_name": "Ibrahim", "last_name": "Remedios", **fields})


class TestGetContactPhone(FrappeTestCase):
	def test_primary_phone_nos_row_wins_over_other_rows(self):
		doc = _contact(
			phone_nos=[
				{"phone": "5550000001", "is_primary_phone": 0},
				{"phone": "5550000002", "is_primary_phone": 1},
			]
		)
		self.assertEqual(get_contact_phone(doc), "5550000002")

	def test_first_non_empty_phone_nos_row_when_none_primary(self):
		doc = _contact(
			phone_nos=[
				{"phone": "", "is_primary_phone": 0},
				{"phone": "5550000003", "is_primary_phone": 0},
			]
		)
		self.assertEqual(get_contact_phone(doc), "5550000003")

	def test_mobile_no_used_when_no_phone_nos(self):
		doc = _contact(mobile_no="5550000004", phone_nos=[])
		self.assertEqual(get_contact_phone(doc), "5550000004")

	def test_empty_when_no_phone_anywhere(self):
		self.assertEqual(get_contact_phone(_contact(phone_nos=[])), "")


class TestBuildContactPayloadPhone(FrappeTestCase):
	def test_only_mobile_no_populates_phone1(self):
		payload = build_contact_payload(_contact(mobile_no="5550000010", phone_nos=[]))
		self.assertEqual(payload["phone1"], "5550000010")

	def test_only_non_primary_phone_nos_row_populates_phone1(self):
		payload = build_contact_payload(_contact(phone_nos=[{"phone": "5550000011", "is_primary_phone": 0}]))
		self.assertEqual(payload["phone1"], "5550000011")
		self.assertEqual(payload["phone_type_id1"], 1)

	def test_primary_phone_nos_row_populates_phone1(self):
		payload = build_contact_payload(_contact(phone_nos=[{"phone": "5550000012", "is_primary_phone": 1}]))
		self.assertEqual(payload["phone1"], "5550000012")


class TestIcorpErrorText(FrappeTestCase):
	def test_prefers_raw_text_and_appends_status(self):
		self.assertEqual(
			icorp_error_text(dict(_NON_JSON_ERROR)),
			"Must have a least 1 contact phone number. (HTTP 400)",
		)

	def test_text_is_stripped(self):
		self.assertEqual(icorp_error_text({"error": "x", "text": "  spaced out \n"}), "spaced out")

	def test_text_truncated_to_limit(self):
		long_text = "a" * (_ERROR_TEXT_MAX_CHARS + 50)
		result = icorp_error_text({"error": "Invalid JSON response", "text": long_text})
		self.assertEqual(result, "a" * _ERROR_TEXT_MAX_CHARS + "...")

	def test_falls_back_to_error_without_text(self):
		self.assertEqual(icorp_error_text({"error": "bad contact"}), "bad contact")

	def test_status_appended_to_fallback_error(self):
		self.assertEqual(icorp_error_text({"error": "boom", "status_code": 500}), "boom (HTTP 500)")


class TestCreateWithErrorNonJson(FrappeTestCase):
	def setUp(self):
		super().setUp()
		patcher_post = patch(_ICORP_POST)
		patcher_log = patch(_LOG_ERROR)
		self.mock_post = patcher_post.start()
		self.mock_log = patcher_log.start()
		self.addCleanup(patcher_post.stop)
		self.addCleanup(patcher_log.stop)

	def test_contact_non_json_error_returns_icorp_text(self):
		self.mock_post.return_value = dict(_NON_JSON_ERROR)
		contact_id, error = create_icorp_contact_with_error(
			_contact(phone_nos=[{"phone": "5550000020", "is_primary_phone": 1}])
		)
		self.assertIsNone(contact_id)
		self.assertIn("Must have a least 1 contact phone number.", error)
		self.mock_log.assert_called_once()
		self.assertEqual(self.mock_log.call_args.args[0], "iCorp: failed to create contact")

	def test_client_non_json_error_returns_icorp_text(self):
		self.mock_post.return_value = dict(_NON_JSON_ERROR)
		client_id, error = create_icorp_client_with_error("Acme", 123)
		self.assertIsNone(client_id)
		self.assertEqual(error, "Must have a least 1 contact phone number. (HTTP 400)")
		self.assertEqual(self.mock_log.call_args.args[0], "iCorp: failed to create client 'Acme'")
