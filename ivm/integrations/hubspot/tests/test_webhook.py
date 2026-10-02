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
	"""_route_event routing via routing.route()"""

	def test_ignores_non_routable_subscription_types(self):
		"""object.deletion, object.merge, object.restore -> returns 'ignored', no routing.route call"""
		for sub_type in ["object.deletion", "object.merge", "object.restore"]:
			with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
				result = _route_event(
					{"subscriptionType": sub_type, "objectTypeId": "0-3", "objectId": "123"}
				)
				self.assertEqual(result, "ignored")
				mock_route.assert_not_called()

	def test_creation_routes_via_routing_route(self):
		"""object.creation -> calls routing.route and returns its result"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			mock_route.return_value = "enqueued"
			result = _route_event(
				{"subscriptionType": "object.creation", "objectTypeId": "0-3", "objectId": "123"}
			)
			self.assertEqual(result, "enqueued")
			mock_route.assert_called_once_with("0-3", "123")

	def test_property_change_routes_via_routing_route(self):
		"""object.propertyChange -> calls routing.route and returns its result"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			mock_route.return_value = "dropped"
			result = _route_event(
				{"subscriptionType": "object.propertyChange", "objectTypeId": "0-3", "objectId": "456"}
			)
			self.assertEqual(result, "dropped")
			mock_route.assert_called_once_with("0-3", "456")

	def test_missing_object_id_is_ignored(self):
		"""Missing objectId -> returns 'ignored', no routing.route call"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			result = _route_event({"subscriptionType": "object.creation", "objectTypeId": "0-3"})
			self.assertEqual(result, "ignored")
			mock_route.assert_not_called()

	def test_association_change_routes_both_sides(self):
		"""object.associationChange -> routes both from and to sides, prefers 'enqueued'"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			mock_route.side_effect = ["enqueued", "dropped"]
			result = _route_event(
				{
					"subscriptionType": "object.associationChange",
					"fromObjectTypeId": "0-3",
					"fromObjectId": "111",
					"toObjectTypeId": "2-226377266",
					"toObjectId": "222",
				}
			)
			self.assertEqual(result, "enqueued")
			self.assertEqual(mock_route.call_count, 2)
			calls = mock_route.call_args_list
			self.assertEqual(calls[0][0], ("0-3", "111"))
			self.assertEqual(calls[1][0], ("2-226377266", "222"))

	def test_association_change_both_sides_dropped_returns_first_outcome(self):
		"""object.associationChange both sides dropped -> returns 'dropped'"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			mock_route.side_effect = ["dropped", "dropped"]
			result = _route_event(
				{
					"subscriptionType": "object.associationChange",
					"fromObjectTypeId": "0-3",
					"fromObjectId": "111",
					"toObjectTypeId": "2-226377266",
					"toObjectId": "222",
				}
			)
			self.assertEqual(result, "dropped")

	def test_association_change_missing_from_id_only_routes_to_side(self):
		"""object.associationChange missing fromObjectId -> routes only to side"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			mock_route.return_value = "enqueued"
			result = _route_event(
				{
					"subscriptionType": "object.associationChange",
					"fromObjectTypeId": "0-3",
					"toObjectTypeId": "2-226377266",
					"toObjectId": "222",
				}
			)
			self.assertEqual(result, "enqueued")
			mock_route.assert_called_once_with("2-226377266", "222")

	def test_association_change_both_ids_missing_returns_ignored(self):
		"""object.associationChange both IDs missing -> returns 'ignored'"""
		with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
			result = _route_event(
				{
					"subscriptionType": "object.associationChange",
					"fromObjectTypeId": "0-3",
					"toObjectTypeId": "2-226377266",
				}
			)
			self.assertEqual(result, "ignored")
			mock_route.assert_not_called()


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
				with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
					mock_route.return_value = "enqueued"
					with patch("frappe.enqueue"):
						result = handle_webhook()
						self.assertEqual(result["status"], "ok")
						self.assertIn("results", result)
						self.assertEqual(result["results"].get("enqueued"), 2)

	def test_valid_request_one_of_two_events_fails_returns_ok_with_counts(self):
		"""Valid request, 1 of 2 events fails during routing still returns 200 with results counts."""
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
				with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
					mock_route.side_effect = [ValueError("route failed"), "enqueued"]
					with patch("frappe.enqueue"):
						with patch("frappe.log_error"):
							result = handle_webhook()
							self.assertEqual(result["status"], "ok")
							self.assertIn("results", result)
							self.assertEqual(result["results"].get("failed"), 1)
							self.assertEqual(result["results"].get("enqueued"), 1)

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

	def test_dev_relay_not_enqueued_when_unconfigured(self):
		"""Dev relay not enqueued when hubspot_dev_relay_url not configured"""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "deal_1",
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

		# frappe.conf is a dict-like config object, not a plain instance with
		# its own `.get` — unittest.mock.patch("frappe.conf.get") fails to
		# locate an attribute to patch on it (TypeError: 'NoneType' object is
		# not subscriptable from mock's internal __dict__ lookup). Use
		# patch.dict on the conf object itself instead, which Frappe's own
		# test suite uses for exactly this purpose.
		with patch("frappe.request", mock_request):
			with patch("ivm.integrations.hubspot.api.verify_signature") as mock_verify:
				mock_verify.return_value = True
				with patch.dict(frappe.conf, {"hubspot_dev_relay_url": None}):
					with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
						mock_route.return_value = "enqueued"
						with patch("frappe.enqueue") as mock_enqueue:
							handle_webhook()
							# enqueue should only be called for routing, not for dev relay
							for call in mock_enqueue.call_args_list:
								self.assertNotIn("_forward_to_dev", str(call))

	def test_dev_relay_enqueued_when_configured(self):
		"""Dev relay enqueued when hubspot_dev_relay_url is configured"""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.creation",
				"objectId": "deal_1",
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
				with patch.dict(frappe.conf, {"hubspot_dev_relay_url": "https://dev.example.com/webhook"}):
					with patch("ivm.integrations.hubspot.webhook.routing.route") as mock_route:
						mock_route.return_value = "enqueued"
						with patch("frappe.enqueue") as mock_enqueue:
							handle_webhook()
							# enqueue should be called for dev relay
							found_relay = False
							for call in mock_enqueue.call_args_list:
								if "_forward_to_dev" in str(call):
									found_relay = True
									break
							self.assertTrue(found_relay)

	def test_deletion_event_counted_as_ignored(self):
		"""object.deletion event -> counted as 'ignored' in results"""
		current_ts_ms = int(time.time() * 1000)
		events = [
			{
				"objectTypeId": DEAL_TYPE_ID,
				"subscriptionType": "object.deletion",
				"objectId": "deal_1",
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
				with patch("frappe.enqueue"):
					result = handle_webhook()
					self.assertEqual(result["status"], "ok")
					self.assertIn("results", result)
					self.assertEqual(result["results"].get("ignored"), 1)
