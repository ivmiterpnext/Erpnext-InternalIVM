"""Tests for ivm.integrations.hubspot.webhook"""

import json
import time
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.constants import (
	CALL_TYPE_ID,
	COMPANY_TYPE_ID,
	CONTACT_TYPE_ID,
	DEAL_TYPE_ID,
	DEPLOYMENT_SITE_TYPE_ID,
	EMAIL_TYPE_ID,
	ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID,
	MACHINE_TYPE_TO_CHILD_TABLE,
	NOTE_TYPE_ID,
	SMARTLOCKER_TYPE_ID,
	SMARTSTATION_TYPE_ID,
)
from ivm.integrations.hubspot.webhook import (
	MAX_TIMESTAMP_AGE_SECONDS,
	_engagement_kwargs,
	_machine_kwargs,
	_route_event,
	_verify_request,
	handle_webhook,
)


class TestVerifyRequest(FrappeTestCase):
	"""_verify_request signature and timestamp validation"""

	def test_valid_signature_and_fresh_timestamp_succeeds(self):
		"""Valid signature + fresh timestamp raises no exception."""
		current_ts_ms = int(time.time() * 1000)
		body = '{"test": "data"}'
		signature = "valid_sig"

		with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
			mock_verify.return_value = True
			_verify_request(body, signature, str(current_ts_ms))
			mock_verify.assert_called_once_with(body, signature)

	def test_expired_timestamp_raises_authentication_error(self):
		"""Timestamp older than MAX_TIMESTAMP_AGE_SECONDS raises AuthenticationError."""
		stale_ts_ms = int((time.time() - MAX_TIMESTAMP_AGE_SECONDS - 10) * 1000)
		body = '{"test": "data"}'
		signature = "valid_sig"

		with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
			mock_verify.return_value = True
			with self.assertRaises(frappe.AuthenticationError):
				_verify_request(body, signature, str(stale_ts_ms))

	def test_invalid_non_integer_timestamp_raises_authentication_error(self):
		"""Non-integer timestamp raises AuthenticationError."""
		body = '{"test": "data"}'
		signature = "valid_sig"

		with self.assertRaises(frappe.AuthenticationError):
			_verify_request(body, signature, "not_a_number")

	def test_invalid_signature_raises_authentication_error(self):
		"""Invalid signature raises AuthenticationError."""
		current_ts_ms = int(time.time() * 1000)
		body = '{"test": "data"}'
		signature = "invalid_sig"

		with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
			mock_verify.return_value = False
			with self.assertRaises(frappe.AuthenticationError):
				_verify_request(body, signature, str(current_ts_ms))


class TestRouteEvent(FrappeTestCase):
	"""_route_event handler routing and enqueue logic"""

	def test_known_object_type_and_subscription_type_enqueues_with_correct_kwargs(self):
		"""Known object type + subscription type enqueues with correct method and kwargs."""
		event = {
			"objectTypeId": DEAL_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "12345",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			mock_enqueue.assert_called_once()
			call_args = mock_enqueue.call_args
			self.assertIn("ivm.integrations.hubspot.deal_handler.handle_deal_created", str(call_args))
			self.assertEqual(call_args.kwargs["hubspot_deal_id"], "12345")
			self.assertEqual(call_args.kwargs["hubspot_user_id"], "user_123")
			self.assertEqual(call_args.kwargs["queue"], "long")
			self.assertTrue(call_args.kwargs["deduplicate"])

	def test_known_object_type_unknown_subscription_type_logs_warning_no_enqueue(self):
		"""Known object type + unknown subscription type logs warning, no enqueue."""
		event = {
			"objectTypeId": DEAL_TYPE_ID,
			"subscriptionType": "unknown.subscription",
			"objectId": "12345",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			with patch("ivm.integrations.hubspot.webhook._logger") as mock_logger:
				_route_event(event)
				mock_enqueue.assert_not_called()
				mock_logger.warning.assert_called_once()
				self.assertIn("No handler for unknown.subscription", mock_logger.warning.call_args[0][0])

	def test_unknown_object_type_logs_warning_no_enqueue(self):
		"""Unknown object type logs warning, no enqueue."""
		event = {
			"objectTypeId": "9-999",
			"subscriptionType": "object.creation",
			"objectId": "12345",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			with patch("ivm.integrations.hubspot.webhook._logger") as mock_logger:
				_route_event(event)
				mock_enqueue.assert_not_called()
				mock_logger.warning.assert_called_once()
				self.assertIn("Unhandled objectTypeId: 9-999", mock_logger.warning.call_args[0][0])

	def test_missing_object_id_returns_without_action(self):
		"""Missing objectId returns without enqueue."""
		event = {
			"objectTypeId": DEAL_TYPE_ID,
			"subscriptionType": "object.creation",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			mock_enqueue.assert_not_called()

	def test_engagement_event_includes_engagement_type_and_id(self):
		"""Engagement event kwargs include engagement_type and engagement_id."""
		event = {
			"objectTypeId": CALL_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "call_456",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			call_args = mock_enqueue.call_args
			self.assertEqual(call_args.kwargs["engagement_type"], "calls")
			self.assertEqual(call_args.kwargs["engagement_id"], "call_456")

	def test_machine_event_includes_machine_type_id_and_hubspot_machine_id(self):
		"""Machine event kwargs include machine_type_id and hubspot_machine_id."""
		event = {
			"objectTypeId": SMARTLOCKER_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "machine_789",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			call_args = mock_enqueue.call_args
			self.assertEqual(call_args.kwargs["machine_type_id"], SMARTLOCKER_TYPE_ID)
			self.assertEqual(call_args.kwargs["hubspot_machine_id"], "machine_789")

	def test_enqueue_exception_logs_error_and_reraises(self):
		"""frappe.enqueue exception logs error and re-raises."""
		event = {
			"objectTypeId": DEAL_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "12345",
			"userId": "user_123",
		}

		enqueue_error = RuntimeError("Enqueue failed")

		with patch("frappe.enqueue") as mock_enqueue:
			mock_enqueue.side_effect = enqueue_error
			with patch("frappe.log_error") as mock_log_error:
				with self.assertRaises(RuntimeError):
					_route_event(event)
				mock_log_error.assert_called_once()
				self.assertIn("failed to enqueue", mock_log_error.call_args.kwargs["title"])

	def test_contact_event_enqueues_with_contact_id(self):
		"""Contact event enqueues with hubspot_contact_id."""
		event = {
			"objectTypeId": CONTACT_TYPE_ID,
			"subscriptionType": "object.propertyChange",
			"objectId": "contact_111",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			call_args = mock_enqueue.call_args
			self.assertEqual(call_args.kwargs["hubspot_contact_id"], "contact_111")
			self.assertIn("contact_handler.handle_contact_updated", str(call_args))

	def test_company_event_enqueues_with_company_id(self):
		"""Company event enqueues with hubspot_company_id."""
		event = {
			"objectTypeId": COMPANY_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "company_222",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			call_args = mock_enqueue.call_args
			self.assertEqual(call_args.kwargs["hubspot_company_id"], "company_222")
			self.assertIn("company_handler.handle_company_created", str(call_args))

	def test_site_event_enqueues_with_site_id(self):
		"""Deployment site event enqueues with hubspot_site_id."""
		event = {
			"objectTypeId": DEPLOYMENT_SITE_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "site_333",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			call_args = mock_enqueue.call_args
			self.assertEqual(call_args.kwargs["hubspot_site_id"], "site_333")
			self.assertIn("deployment_site_handler.handle_site_webhook", str(call_args))

	def test_job_id_includes_object_type_id_object_id_and_subscription_type(self):
		"""Job ID is constructed from object_type_id, object_id, and subscription_type."""
		event = {
			"objectTypeId": DEAL_TYPE_ID,
			"subscriptionType": "object.creation",
			"objectId": "12345",
			"userId": "user_123",
		}

		with patch("frappe.enqueue") as mock_enqueue:
			_route_event(event)
			call_args = mock_enqueue.call_args
			expected_job_id = f"hubspot_{DEAL_TYPE_ID}_12345_object.creation"
			self.assertEqual(call_args.kwargs["job_id"], expected_job_id)


class TestHandleWebhook(FrappeTestCase):
	"""handle_webhook integration-level request handling"""

	def test_valid_request_with_two_events_both_route_successfully_returns_ok(self):
		"""Valid request with 2 events that both route successfully returns ok status."""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "deal_1",
				"userId": "user_1",
			},
			{
				"objectTypeId": CONTACT_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "contact_1",
				"userId": "user_1",
			},
		]
		request_body = json.dumps(events)

		mock_request = MagicMock()
		mock_request.get_data.return_value = request_body
		mock_request.headers.get.side_effect = lambda key, default="": {
			"X-HubSpot-Signature": "valid_sig",
			"X-HubSpot-Request-Timestamp": str(current_ts_ms),
			"Content-Type": "application/json",
		}.get(key, default)

		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = True
				with patch("frappe.enqueue") as mock_enqueue:
					result = handle_webhook()
					self.assertEqual(result["status"], "ok")
					self.assertEqual(mock_enqueue.call_count, 3)  # 1 for dev relay + 2 for events

	def test_valid_request_one_of_two_events_fails_returns_error_with_500_status(self):
		"""Valid request, 1 of 2 events fails during routing returns error dict with 500 status."""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "deal_1",
				"userId": "user_1",
			},
			{
				"objectTypeId": CONTACT_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "contact_1",
				"userId": "user_1",
			},
		]
		request_body = json.dumps(events)

		mock_request = MagicMock()
		mock_request.get_data.return_value = request_body
		mock_request.headers.get.side_effect = lambda key, default="": {
			"X-HubSpot-Signature": "valid_sig",
			"X-HubSpot-Request-Timestamp": str(current_ts_ms),
			"Content-Type": "application/json",
		}.get(key, default)

		def enqueue_side_effect(*args, **kwargs):
			# First call (dev relay) succeeds, second call (first event) succeeds,
			# third call (second event) fails
			if enqueue_side_effect.call_count == 3:
				raise RuntimeError("Enqueue failed for second event")
			enqueue_side_effect.call_count += 1

		enqueue_side_effect.call_count = 1

		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = True
				with patch("frappe.enqueue") as mock_enqueue:
					mock_enqueue.side_effect = enqueue_side_effect
					with patch("frappe.log_error"):
						result = handle_webhook()
						self.assertEqual(result["status"], "error")
						self.assertIn("One or more events", result["message"])

	def test_invalid_json_body_logs_error_returns_error_dict_no_exception(self):
		"""Invalid JSON body logs error, returns error dict, no exception propagates."""
		current_ts_ms = int(time.time() * 1000)
		request_body = "not valid json {"

		mock_request = MagicMock()
		mock_request.get_data.return_value = request_body
		mock_request.headers.get.side_effect = lambda key, default="": {
			"X-HubSpot-Signature": "valid_sig",
			"X-HubSpot-Request-Timestamp": str(current_ts_ms),
			"Content-Type": "application/json",
		}.get(key, default)

		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = True
				with patch("frappe.enqueue"):
					with patch("frappe.log_error") as mock_log_error:
						result = handle_webhook()
						self.assertEqual(result["status"], "error")
						self.assertIn("Invalid JSON", result["message"])
						mock_log_error.assert_called_once()
						self.assertIn("invalid JSON payload", mock_log_error.call_args.kwargs["title"])

	def test_signature_verification_failure_raises_authentication_error_before_event_processing(self):
		"""Signature verification failure raises AuthenticationError before event processing."""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "deal_1",
				"userId": "user_1",
			},
		]
		request_body = json.dumps(events)

		mock_request = MagicMock()
		mock_request.get_data.return_value = request_body
		mock_request.headers.get.side_effect = lambda key, default="": {
			"X-HubSpot-Signature": "invalid_sig",
			"X-HubSpot-Request-Timestamp": str(current_ts_ms),
			"Content-Type": "application/json",
		}.get(key, default)

		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = False
				with patch("frappe.enqueue") as mock_enqueue:
					with self.assertRaises(frappe.AuthenticationError):
						handle_webhook()
					# Verify no event processing happened (only dev relay enqueue would have been called)
					# but since verify_request raises before that, no enqueue at all
					mock_enqueue.assert_not_called()

	def test_dev_relay_enqueued_on_valid_request(self):
		"""Dev relay forward is enqueued on valid request."""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "deal_1",
				"userId": "user_1",
			},
		]
		request_body = json.dumps(events)

		mock_request = MagicMock()
		mock_request.get_data.return_value = request_body
		mock_request.headers.get.side_effect = lambda key, default="": {
			"X-HubSpot-Signature": "valid_sig",
			"X-HubSpot-Request-Timestamp": str(current_ts_ms),
			"Content-Type": "application/json",
		}.get(key, default)

		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = True
				with patch("frappe.enqueue") as mock_enqueue:
					handle_webhook()
					# First call should be dev relay
					first_call = mock_enqueue.call_args_list[0]
					self.assertIn("_forward_to_dev", str(first_call))
					self.assertEqual(first_call.kwargs["queue"], "short")

	def test_empty_events_list_returns_ok(self):
		"""Empty events list returns ok status."""
		current_ts_ms = int(time.time() * 1000)
		events = []
		request_body = json.dumps(events)

		mock_request = MagicMock()
		mock_request.get_data.return_value = request_body
		mock_request.headers.get.side_effect = lambda key, default="": {
			"X-HubSpot-Signature": "valid_sig",
			"X-HubSpot-Request-Timestamp": str(current_ts_ms),
			"Content-Type": "application/json",
		}.get(key, default)

		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = True
				with patch("frappe.enqueue"):
					result = handle_webhook()
					self.assertEqual(result["status"], "ok")


class TestEngagementKwargs(FrappeTestCase):
	"""_engagement_kwargs builder function"""

	def test_call_engagement_returns_calls_type_and_engagement_id(self):
		"""Call engagement returns engagement_type='calls' and engagement_id."""
		event = {"objectTypeId": CALL_TYPE_ID}
		kwargs = _engagement_kwargs("call_123", event)
		self.assertEqual(kwargs["engagement_type"], "calls")
		self.assertEqual(kwargs["engagement_id"], "call_123")

	def test_note_engagement_returns_notes_type_and_engagement_id(self):
		"""Note engagement returns engagement_type='notes' and engagement_id."""
		event = {"objectTypeId": NOTE_TYPE_ID}
		kwargs = _engagement_kwargs("note_456", event)
		self.assertEqual(kwargs["engagement_type"], "notes")
		self.assertEqual(kwargs["engagement_id"], "note_456")

	def test_email_engagement_returns_emails_type_and_engagement_id(self):
		"""Email engagement returns engagement_type='emails' and engagement_id."""
		event = {"objectTypeId": EMAIL_TYPE_ID}
		kwargs = _engagement_kwargs("email_789", event)
		self.assertEqual(kwargs["engagement_type"], "emails")
		self.assertEqual(kwargs["engagement_id"], "email_789")

	def test_unknown_engagement_type_returns_empty_string(self):
		"""Unknown engagement type returns empty string for engagement_type."""
		event = {"objectTypeId": "9-999"}
		kwargs = _engagement_kwargs("unknown_123", event)
		self.assertEqual(kwargs["engagement_type"], "")
		self.assertEqual(kwargs["engagement_id"], "unknown_123")


class TestMachineKwargs(FrappeTestCase):
	"""_machine_kwargs builder function"""

	def test_smartlocker_machine_returns_machine_type_id_and_hubspot_machine_id(self):
		"""SmartLocker machine returns machine_type_id and hubspot_machine_id."""
		event = {"objectTypeId": SMARTLOCKER_TYPE_ID}
		kwargs = _machine_kwargs("locker_123", event)
		self.assertEqual(kwargs["machine_type_id"], SMARTLOCKER_TYPE_ID)
		self.assertEqual(kwargs["hubspot_machine_id"], "locker_123")

	def test_smartstation_machine_returns_machine_type_id_and_hubspot_machine_id(self):
		"""SmartStation machine returns machine_type_id and hubspot_machine_id."""
		event = {"objectTypeId": SMARTSTATION_TYPE_ID}
		kwargs = _machine_kwargs("station_456", event)
		self.assertEqual(kwargs["machine_type_id"], SMARTSTATION_TYPE_ID)
		self.assertEqual(kwargs["hubspot_machine_id"], "station_456")

	def test_missing_object_type_id_returns_empty_string_for_machine_type_id(self):
		"""Missing objectTypeId returns empty string for machine_type_id."""
		event = {}
		kwargs = _machine_kwargs("machine_789", event)
		self.assertEqual(kwargs["machine_type_id"], "")
		self.assertEqual(kwargs["hubspot_machine_id"], "machine_789")
