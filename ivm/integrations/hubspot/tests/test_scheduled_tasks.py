"""Tests for ivm.integrations.hubspot.scheduled_tasks"""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.scheduled_tasks import (
	_sync_one_email,
	sync_inbound_emails,
)


class TestSyncInboundEmails(FrappeTestCase):
	"""sync_inbound_emails scheduled task"""

	def test_open_deals_with_new_emails_enqueues_per_email(self):
		"""Open deals exist with new emails -> frappe.enqueue called once per new email_id"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.db.sql") as mock_sql:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.enqueue") as mock_enqueue:
					with patch(
						"ivm.integrations.hubspot.scheduled_tasks.api.get_deal_email_ids_batch"
					) as mock_batch:
						mock_get_all.return_value = [
							{"name": "Deal-001", "custom_hubspot_deal_id": "hs-deal-1"},
							{"name": "Deal-002", "custom_hubspot_deal_id": "hs-deal-2"},
						]
						mock_batch.return_value = {
							"hs-deal-1": ["email-1", "email-2"],
							"hs-deal-2": ["email-3"],
						}
						mock_sql.return_value = []
						sync_inbound_emails()
						self.assertEqual(mock_enqueue.call_count, 3)
						calls = mock_enqueue.call_args_list
						self.assertEqual(calls[0][1]["email_id"], "email-1")
						self.assertEqual(calls[0][1]["crm_deal_names"], ["Deal-001"])
						self.assertEqual(calls[1][1]["email_id"], "email-2")
						self.assertEqual(calls[1][1]["crm_deal_names"], ["Deal-001"])
						self.assertEqual(calls[2][1]["email_id"], "email-3")
						self.assertEqual(calls[2][1]["crm_deal_names"], ["Deal-002"])

	def test_all_emails_already_synced_no_enqueue(self):
		"""All emails already synced -> frappe.enqueue not called"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.db.sql") as mock_sql:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.enqueue") as mock_enqueue:
					with patch(
						"ivm.integrations.hubspot.scheduled_tasks.api.get_deal_email_ids_batch"
					) as mock_batch:
						mock_get_all.return_value = [
							{"name": "Deal-001", "custom_hubspot_deal_id": "hs-deal-1"},
						]
						mock_batch.return_value = {
							"hs-deal-1": ["email-1", "email-2"],
						}
						mock_sql.return_value = [
							("<hubspot-email-email-1>",),
							("<hubspot-email-email-2>",),
						]
						sync_inbound_emails()
						mock_enqueue.assert_not_called()

	def test_no_open_deals_returns_immediately(self):
		"""No open deals found -> returns immediately, no further calls"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.db.sql") as mock_sql:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.enqueue") as mock_enqueue:
					with patch(
						"ivm.integrations.hubspot.scheduled_tasks.api.get_deal_email_ids_batch"
					) as mock_batch:
						mock_get_all.return_value = []
						sync_inbound_emails()
						mock_batch.assert_not_called()
						mock_sql.assert_not_called()
						mock_enqueue.assert_not_called()

	def test_api_batch_fetch_exception_logs_error_returns(self):
		"""api.get_deal_email_ids_batch raises -> logs error, returns without enqueueing"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_deal_email_ids_batch") as mock_batch:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.log_error") as mock_log_error:
					with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.enqueue") as mock_enqueue:
						mock_get_all.return_value = [
							{"name": "Deal-001", "custom_hubspot_deal_id": "hs-deal-1"},
						]
						mock_batch.side_effect = ValueError("API error")
						sync_inbound_emails()
						mock_log_error.assert_called_once()
						mock_enqueue.assert_not_called()

	def test_single_email_multiple_deals_enqueued_once_with_all_deals(self):
		"""Single email associated with multiple deals -> enqueued once with all deal names"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.db.sql") as mock_sql:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.enqueue") as mock_enqueue:
					with patch(
						"ivm.integrations.hubspot.scheduled_tasks.api.get_deal_email_ids_batch"
					) as mock_batch:
						mock_get_all.return_value = [
							{"name": "Deal-001", "custom_hubspot_deal_id": "hs-deal-1"},
							{"name": "Deal-002", "custom_hubspot_deal_id": "hs-deal-2"},
						]
						mock_batch.return_value = {
							"hs-deal-1": ["email-1"],
							"hs-deal-2": ["email-1"],
						}
						mock_sql.return_value = []
						sync_inbound_emails()
						mock_enqueue.assert_called_once()
						call_kwargs = mock_enqueue.call_args[1]
						self.assertEqual(call_kwargs["email_id"], "email-1")
						self.assertIn("Deal-001", call_kwargs["crm_deal_names"])
						self.assertIn("Deal-002", call_kwargs["crm_deal_names"])
						self.assertEqual(len(call_kwargs["crm_deal_names"]), 2)

	def test_mixed_synced_and_new_emails_only_new_enqueued(self):
		"""Mix of synced and new emails -> only new ones enqueued"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.db.sql") as mock_sql:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.enqueue") as mock_enqueue:
					with patch(
						"ivm.integrations.hubspot.scheduled_tasks.api.get_deal_email_ids_batch"
					) as mock_batch:
						mock_get_all.return_value = [
							{"name": "Deal-001", "custom_hubspot_deal_id": "hs-deal-1"},
						]
						mock_batch.return_value = {
							"hs-deal-1": ["email-1", "email-2", "email-3"],
						}
						mock_sql.return_value = [
							("<hubspot-email-email-1>",),
						]
						sync_inbound_emails()
						self.assertEqual(mock_enqueue.call_count, 2)
						calls = mock_enqueue.call_args_list
						enqueued_ids = {call[1]["email_id"] for call in calls}
						self.assertIn("email-2", enqueued_ids)
						self.assertIn("email-3", enqueued_ids)
						self.assertNotIn("email-1", enqueued_ids)


class TestSyncOneEmail(FrappeTestCase):
	"""_sync_one_email background task"""

	def test_normal_flow_calls_api_and_sync_email(self):
		"""Normal flow -> calls api.get_engagement once, then _sync_email per deal"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				mock_get_engagement.return_value = {
					"properties": {
						"hs_email_subject": "Test Subject",
						"hs_email_text": "Test body",
					},
					"createdAt": 1234567890,
				}
				_sync_one_email("email-1", ["Deal-001", "Deal-002"])
				mock_get_engagement.assert_called_once()
				self.assertEqual(mock_sync_email.call_count, 2)
				calls = mock_sync_email.call_args_list
				self.assertEqual(calls[0][0][0], "email-1")
				self.assertEqual(calls[0][0][2], "Deal-001")
				self.assertEqual(calls[1][0][0], "email-1")
				self.assertEqual(calls[1][0][2], "Deal-002")

	def test_api_get_engagement_exception_logged_no_sync(self):
		"""api.get_engagement raises -> logs error, does not call _sync_email"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				with patch("ivm.integrations.hubspot.scheduled_tasks.frappe.log_error") as mock_log_error:
					mock_get_engagement.side_effect = ValueError("API error")
					_sync_one_email("email-1", ["Deal-001"])
					mock_log_error.assert_called_once()
					mock_sync_email.assert_not_called()

	def test_properties_with_created_at_in_response(self):
		"""createdAt in response properties -> included in props dict"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				mock_get_engagement.return_value = {
					"properties": {
						"hs_email_subject": "Test",
						"createdAt": 1234567890,
					},
				}
				_sync_one_email("email-1", ["Deal-001"])
				call_kwargs = mock_sync_email.call_args[0]
				props = call_kwargs[1]
				self.assertIn("createdAt", props)

	def test_created_at_fallback_from_root_level(self):
		"""createdAt not in properties but in root -> added as _createdAt"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				mock_get_engagement.return_value = {
					"properties": {
						"hs_email_subject": "Test",
					},
					"createdAt": 1234567890,
				}
				_sync_one_email("email-1", ["Deal-001"])
				call_kwargs = mock_sync_email.call_args[0]
				props = call_kwargs[1]
				self.assertIn("_createdAt", props)
				self.assertEqual(props["_createdAt"], 1234567890)

	def test_single_deal_name_passed_correctly(self):
		"""Single deal name in list -> passed correctly to _sync_email"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				mock_get_engagement.return_value = {
					"properties": {"hs_email_subject": "Test"},
				}
				_sync_one_email("email-1", ["Deal-001"])
				mock_sync_email.assert_called_once()
				call_kwargs = mock_sync_email.call_args[0]
				self.assertEqual(call_kwargs[2], "Deal-001")

	def test_multiple_deal_names_all_synced(self):
		"""Multiple deal names -> all synced with same email data"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				mock_get_engagement.return_value = {
					"properties": {"hs_email_subject": "Test"},
				}
				_sync_one_email("email-1", ["Deal-001", "Deal-002", "Deal-003"])
				self.assertEqual(mock_sync_email.call_count, 3)
				calls = mock_sync_email.call_args_list
				for i, call in enumerate(calls):
					self.assertEqual(call[0][0], "email-1")
					self.assertEqual(call[0][1], {"hs_email_subject": "Test"})
					self.assertEqual(call[0][2], ["Deal-001", "Deal-002", "Deal-003"][i])

	def test_empty_properties_dict_handled(self):
		"""Empty properties dict in response -> handled gracefully"""
		with patch("ivm.integrations.hubspot.scheduled_tasks.api.get_engagement") as mock_get_engagement:
			with patch(
				"ivm.integrations.hubspot.scheduled_tasks.activity_handler._sync_email"
			) as mock_sync_email:
				mock_get_engagement.return_value = {
					"properties": {},
				}
				_sync_one_email("email-1", ["Deal-001"])
				mock_sync_email.assert_called_once()
				call_kwargs = mock_sync_email.call_args[0]
				self.assertEqual(call_kwargs[1], {})
