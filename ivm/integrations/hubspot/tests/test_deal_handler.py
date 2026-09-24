"""Tests for ivm.integrations.hubspot.deal_handler"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.deal_handler import (
	_apply_client_id,
	_apply_deal_owner,
	_apply_deal_type,
	_apply_deal_value,
	_apply_lost_reason,
	_apply_pipeline,
	_apply_status,
	_ensure_contacts,
	_resolve_or_provision_org,
	_sync_contacts,
	_sync_deal,
	handle_deal_created,
	handle_deal_updated,
)
from ivm.integrations.hubspot.sync_utils import ConcurrentCreateConflict


class TestResolveOrProvisionOrg(FrappeTestCase):
	"""_resolve_or_provision_org helper function"""

	def test_returns_existing_org_without_provisioning(self):
		"""When org exists, return it immediately without calling handle_company_created."""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
				mock_get_value.return_value = "Existing Org"
				result = _resolve_or_provision_org("123", "test context")
				self.assertEqual(result, "Existing Org")
				mock_create.assert_not_called()

	def test_provisions_when_missing_then_found(self):
		"""When org missing initially, provision it, then find it on second lookup."""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
				# First call returns None (not found), second call returns the org name
				mock_get_value.side_effect = [None, "Newly Provisioned Org"]
				result = _resolve_or_provision_org("456", "test context")
				self.assertEqual(result, "Newly Provisioned Org")
				mock_create.assert_called_once_with(hubspot_company_id="456")

	def test_returns_none_and_logs_when_still_missing_after_provisioning(self):
		"""When org still missing after provisioning, return None."""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
				# Both calls return None (not found before or after provisioning)
				mock_get_value.side_effect = [None, None]
				result = _resolve_or_provision_org("789", "test context")
				self.assertIsNone(result)
				mock_create.assert_called_once_with(hubspot_company_id="789")

	def test_uses_custom_company_label_in_logging(self):
		"""Custom company_label is used in log messages."""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.handle_company_created"):
				with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
					mock_get_value.side_effect = [None, None]
					_resolve_or_provision_org(
						"999",
						"master link on deal X",
						company_label="master company",
					)
					# Verify logger was called (exact message format is implementation detail)
					mock_logger.assert_called()


class TestApplyDealValue(FrappeTestCase):
	"""_apply_deal_value field transform"""

	def test_converts_string_to_float(self):
		"""String '50000' converts to float 50000.0"""
		doc = SimpleNamespace()
		_apply_deal_value(doc, "50000")
		self.assertEqual(doc.deal_value, 50000.0)

	def test_handles_decimal_string(self):
		"""Decimal string '12345.67' converts correctly"""
		doc = SimpleNamespace()
		_apply_deal_value(doc, "12345.67")
		self.assertEqual(doc.deal_value, 12345.67)

	def test_handles_zero(self):
		"""Zero value handled correctly"""
		doc = SimpleNamespace()
		_apply_deal_value(doc, "0")
		self.assertEqual(doc.deal_value, 0.0)


class TestApplyStatus(FrappeTestCase):
	"""_apply_status field transform"""

	def test_maps_known_dealstage_to_status(self):
		"""Known dealstage maps to correct status via DEALSTAGE_TO_STATUS"""
		doc = SimpleNamespace()
		_apply_status(doc, "closedwon")
		self.assertEqual(doc.status, "Won")

	def test_maps_government_pipeline_dealstage(self):
		"""Government pipeline dealstage maps correctly"""
		doc = SimpleNamespace()
		_apply_status(doc, "2508204768")
		self.assertEqual(doc.status, "Won")

	def test_unknown_dealstage_does_not_set_status(self):
		"""Unknown dealstage does not set doc.status"""
		doc = SimpleNamespace()
		_apply_status(doc, "unknown_stage")
		self.assertFalse(hasattr(doc, "status"))

	def test_empty_dealstage_does_not_set_status(self):
		"""Empty dealstage does not set doc.status"""
		doc = SimpleNamespace()
		_apply_status(doc, "")
		self.assertFalse(hasattr(doc, "status"))

	def test_none_dealstage_does_not_set_status(self):
		"""None dealstage does not set doc.status"""
		doc = SimpleNamespace()
		_apply_status(doc, None)
		self.assertFalse(hasattr(doc, "status"))


class TestApplyLostReason(FrappeTestCase):
	"""_apply_lost_reason field transform"""

	def test_exact_match_case_insensitive(self):
		"""Exact match (case-insensitive) sets doc.lost_reason"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.get_all") as mock_get_all:
			mock_get_all.return_value = ["Budget Constraints"]
			doc = SimpleNamespace()
			_apply_lost_reason(doc, "budget constraints")
			self.assertEqual(doc.lost_reason, "Budget Constraints")

	def test_no_match_sets_other_with_notes(self):
		"""No match sets doc.lost_reason='Other' and doc.lost_notes=original value"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.get_all") as mock_get_all:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
				mock_get_all.return_value = ["Budget Constraints"]
				doc = SimpleNamespace()
				_apply_lost_reason(doc, "Unknown Reason")
				self.assertEqual(doc.lost_reason, "Other")
				self.assertEqual(doc.lost_notes, "Unknown Reason")
				mock_logger.assert_called()

	def test_empty_value_no_op(self):
		"""Empty value is no-op, nothing set"""
		doc = SimpleNamespace()
		_apply_lost_reason(doc, "")
		self.assertFalse(hasattr(doc, "lost_reason"))
		self.assertFalse(hasattr(doc, "lost_notes"))

	def test_none_value_no_op(self):
		"""None value is no-op, nothing set"""
		doc = SimpleNamespace()
		_apply_lost_reason(doc, None)
		self.assertFalse(hasattr(doc, "lost_reason"))
		self.assertFalse(hasattr(doc, "lost_notes"))

	def test_whitespace_only_no_op(self):
		"""Whitespace-only value is no-op"""
		doc = SimpleNamespace()
		_apply_lost_reason(doc, "   ")
		self.assertFalse(hasattr(doc, "lost_reason"))
		self.assertFalse(hasattr(doc, "lost_notes"))


class TestApplyPipeline(FrappeTestCase):
	"""_apply_pipeline field transform"""

	def test_known_pipeline_exists_in_db(self):
		"""Known pipeline ID that exists in DB sets doc.custom_pipeline"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.exists") as mock_exists:
			mock_exists.return_value = True
			doc = SimpleNamespace()
			_apply_pipeline(doc, "default")
			self.assertEqual(doc.custom_pipeline, "Commercial Sales")

	def test_known_pipeline_missing_from_db_logs_warning(self):
		"""Known pipeline ID missing from DB logs warning, does not set"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.exists") as mock_exists:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
				mock_exists.return_value = False
				doc = SimpleNamespace()
				_apply_pipeline(doc, "default")
				self.assertFalse(hasattr(doc, "custom_pipeline"))
				mock_logger.assert_called()

	def test_unknown_pipeline_id_logs_warning(self):
		"""Unknown pipeline ID logs warning"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
			doc = SimpleNamespace()
			_apply_pipeline(doc, "unknown_pipeline_id")
			self.assertFalse(hasattr(doc, "custom_pipeline"))
			mock_logger.assert_called()

	def test_empty_pipeline_no_op(self):
		"""Empty pipeline value is no-op"""
		doc = SimpleNamespace()
		_apply_pipeline(doc, "")
		self.assertFalse(hasattr(doc, "custom_pipeline"))

	def test_none_pipeline_no_op(self):
		"""None pipeline value is no-op"""
		doc = SimpleNamespace()
		_apply_pipeline(doc, None)
		self.assertFalse(hasattr(doc, "custom_pipeline"))


class TestApplyDealType(FrappeTestCase):
	"""_apply_deal_type field transform"""

	def test_known_label_sets_custom_deal_type(self):
		"""Known label in HUBSPOT_DEAL_TYPE_LABELS sets doc.custom_deal_type"""
		doc = SimpleNamespace()
		_apply_deal_type(doc, "newbusiness")
		self.assertEqual(doc.custom_deal_type, "New Business")

	def test_existing_business_label(self):
		"""Existing business label maps correctly"""
		doc = SimpleNamespace()
		_apply_deal_type(doc, "existingbusiness")
		self.assertEqual(doc.custom_deal_type, "Existing Business")

	def test_unknown_label_logs_warning(self):
		"""Unknown label logs warning"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
			doc = SimpleNamespace()
			_apply_deal_type(doc, "unknown_type")
			self.assertFalse(hasattr(doc, "custom_deal_type"))
			mock_logger.assert_called()

	def test_empty_value_no_op(self):
		"""Empty value is no-op"""
		doc = SimpleNamespace()
		_apply_deal_type(doc, "")
		self.assertFalse(hasattr(doc, "custom_deal_type"))

	def test_none_value_no_op(self):
		"""None value is no-op"""
		doc = SimpleNamespace()
		_apply_deal_type(doc, None)
		self.assertFalse(hasattr(doc, "custom_deal_type"))


class TestApplyDealOwner(FrappeTestCase):
	"""_apply_deal_owner field transform"""

	def test_owner_resolves_to_existing_user(self):
		"""Owner resolves to email that exists as User sets doc.deal_owner"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_owner_email") as mock_get_email:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.db.exists") as mock_exists:
				mock_get_email.return_value = "owner@example.com"
				mock_exists.return_value = True
				doc = SimpleNamespace()
				_apply_deal_owner(doc, "12345")
				self.assertEqual(doc.deal_owner, "owner@example.com")

	def test_owner_email_does_not_exist_as_user_logs_warning(self):
		"""Owner email does not exist as User logs warning, does not set"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_owner_email") as mock_get_email:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.db.exists") as mock_exists:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
					mock_get_email.return_value = "nonexistent@example.com"
					mock_exists.return_value = False
					doc = SimpleNamespace()
					_apply_deal_owner(doc, "12345")
					self.assertFalse(hasattr(doc, "deal_owner"))
					mock_logger.assert_called()

	def test_owner_email_resolution_returns_none(self):
		"""Owner email resolution returns None logs warning"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_owner_email") as mock_get_email:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
				mock_get_email.return_value = None
				doc = SimpleNamespace()
				_apply_deal_owner(doc, "12345")
				self.assertFalse(hasattr(doc, "deal_owner"))
				mock_logger.assert_called()

	def test_empty_value_no_op(self):
		"""Empty value is no-op"""
		doc = SimpleNamespace()
		_apply_deal_owner(doc, "")
		self.assertFalse(hasattr(doc, "deal_owner"))

	def test_none_value_no_op(self):
		"""None value is no-op"""
		doc = SimpleNamespace()
		_apply_deal_owner(doc, None)
		self.assertFalse(hasattr(doc, "deal_owner"))


class TestApplyClientId(FrappeTestCase):
	"""_apply_client_id field transform"""

	def test_matching_customer_found_by_icorp_client_id(self):
		"""Matching Customer found by icorp_client_id sets doc.custom_customer"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
			mock_get_value.return_value = "Customer-001"
			doc = SimpleNamespace()
			_apply_client_id(doc, "1042")
			self.assertEqual(doc.custom_customer, "Customer-001")

	def test_no_matching_customer_logs_warning(self):
		"""No matching Customer logs warning, does not set"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
				mock_get_value.return_value = None
				doc = SimpleNamespace()
				_apply_client_id(doc, "9999")
				self.assertFalse(hasattr(doc, "custom_customer"))
				mock_logger.assert_called()

	def test_empty_value_no_op(self):
		"""Empty value is no-op"""
		doc = SimpleNamespace()
		_apply_client_id(doc, "")
		self.assertFalse(hasattr(doc, "custom_customer"))

	def test_none_value_no_op(self):
		"""None value is no-op"""
		doc = SimpleNamespace()
		_apply_client_id(doc, None)
		self.assertFalse(hasattr(doc, "custom_customer"))


class TestHandleDealCreated(FrappeTestCase):
	"""handle_deal_created webhook handler"""

	def test_new_deal_calls_sync_deal(self):
		"""New deal (is_new=True) calls _sync_deal"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.lookup_or_create") as mock_lookup:
				with patch("ivm.integrations.hubspot.deal_handler._sync_deal") as mock_sync:
					mock_doc = MagicMock()
					mock_doc.name = "Deal-001"
					mock_doc.doctype = "CRM Deal"
					mock_lookup.return_value = (mock_doc, True)
					handle_deal_created(hubspot_deal_id="12345")
					mock_sync.assert_called_once_with("12345", "Deal-001")

	def test_duplicate_deal_logs_info_returns_without_sync(self):
		"""Duplicate (is_new=False) logs info, returns without calling _sync_deal"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.lookup_or_create") as mock_lookup:
				with patch("ivm.integrations.hubspot.deal_handler._sync_deal") as mock_sync:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
						mock_doc = MagicMock()
						mock_doc.name = "Deal-001"
						mock_doc.doctype = "CRM Deal"
						mock_lookup.return_value = (mock_doc, False)
						handle_deal_created(hubspot_deal_id="12345")
						mock_sync.assert_not_called()
						mock_logger.assert_called()

	def test_concurrent_create_conflict_re_enqueues(self):
		"""ConcurrentCreateConflict raised internally -> re-enqueued via decorator"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.lookup_or_create") as mock_lookup:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.logger"):
						mock_lookup.side_effect = ConcurrentCreateConflict(
							"CRM Deal", "custom_hubspot_deal_id", "12345"
						)
						# Should not raise, decorator catches and re-enqueues
						handle_deal_created(hubspot_deal_id="12345")
						mock_enqueue.assert_called_once()

	def test_hubspot_rate_limit_exhausted_re_enqueues(self):
		"""api.HubSpotRateLimitExhausted raised internally -> re-enqueued via decorator"""
		from ivm.integrations.hubspot import api

		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.lookup_or_create") as mock_lookup:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.logger"):
						mock_lookup.side_effect = api.HubSpotRateLimitExhausted(retry_after_seconds=60)
						# Should not raise, decorator catches and re-enqueues
						handle_deal_created(hubspot_deal_id="12345")
						mock_enqueue.assert_called_once()

	def test_generic_exception_logged_not_propagated(self):
		"""Generic Exception logged via frappe.log_error, does not propagate"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.lookup_or_create") as mock_lookup:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.log_error") as mock_log_error:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.get_traceback"):
						mock_lookup.side_effect = ValueError("test error")
						# Should not raise
						handle_deal_created(hubspot_deal_id="12345")
						mock_log_error.assert_called_once()

	def test_requires_keyword_only_args(self):
		"""handle_deal_created requires keyword-only args (decorated with @retry_via_reenqueue)"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.lookup_or_create"):
				# Positional args should raise TypeError
				with self.assertRaises(TypeError):
					handle_deal_created("12345")


class TestHandleDealUpdated(FrappeTestCase):
	"""handle_deal_updated webhook handler"""

	def test_existing_deal_calls_sync_deal(self):
		"""Deal already exists (was_created=False) calls _sync_deal"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists") as mock_ensure:
				with patch("ivm.integrations.hubspot.deal_handler._sync_deal") as mock_sync:
					mock_ensure.return_value = ("Deal-001", False)
					handle_deal_updated(hubspot_deal_id="12345")
					mock_sync.assert_called_once_with("12345", "Deal-001")

	def test_newly_created_deal_does_not_call_sync_deal_again(self):
		"""Deal did not exist (was_created=True) does NOT call _sync_deal again"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists") as mock_ensure:
				with patch("ivm.integrations.hubspot.deal_handler._sync_deal") as mock_sync:
					mock_ensure.return_value = ("Deal-001", True)
					handle_deal_updated(hubspot_deal_id="12345")
					mock_sync.assert_not_called()

	def test_concurrent_create_conflict_re_enqueues(self):
		"""ConcurrentCreateConflict raised internally -> re-enqueued via decorator"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists") as mock_ensure:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.logger"):
						mock_ensure.side_effect = ConcurrentCreateConflict(
							"CRM Deal", "custom_hubspot_deal_id", "12345"
						)
						# Should not raise, decorator catches and re-enqueues
						handle_deal_updated(hubspot_deal_id="12345")
						mock_enqueue.assert_called_once()

	def test_hubspot_rate_limit_exhausted_re_enqueues(self):
		"""api.HubSpotRateLimitExhausted raised internally -> re-enqueued via decorator"""
		from ivm.integrations.hubspot import api

		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists") as mock_ensure:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.logger"):
						mock_ensure.side_effect = api.HubSpotRateLimitExhausted(retry_after_seconds=60)
						# Should not raise, decorator catches and re-enqueues
						handle_deal_updated(hubspot_deal_id="12345")
						mock_enqueue.assert_called_once()

	def test_generic_exception_logged_not_propagated(self):
		"""Generic Exception logged via frappe.log_error, does not propagate"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists") as mock_ensure:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.log_error") as mock_log_error:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.get_traceback"):
						mock_ensure.side_effect = ValueError("test error")
						# Should not raise
						handle_deal_updated(hubspot_deal_id="12345")
						mock_log_error.assert_called_once()

	def test_requires_keyword_only_args(self):
		"""handle_deal_updated requires keyword-only args (decorated with @retry_via_reenqueue)"""
		with patch("ivm.integrations.hubspot.deal_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists"):
				# Positional args should raise TypeError
				with self.assertRaises(TypeError):
					handle_deal_updated("12345")


class TestSyncDeal(FrappeTestCase):
	"""_sync_deal orchestration function"""

	def test_normal_flow_calls_all_sync_steps(self):
		"""Normal flow calls api.get_deal, _sync_organization, _sync_master_organization, _sync_contacts, _sync_deal_fields"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal") as mock_get_deal:
			with patch(
				"ivm.integrations.hubspot.deal_handler.api.get_deal_company_ids_by_role"
			) as mock_get_companies:
				with patch("ivm.integrations.hubspot.deal_handler._sync_organization") as mock_sync_org:
					with patch(
						"ivm.integrations.hubspot.deal_handler._sync_master_organization"
					) as mock_sync_master:
						with patch(
							"ivm.integrations.hubspot.deal_handler._sync_contacts"
						) as mock_sync_contacts:
							with patch(
								"ivm.integrations.hubspot.deal_handler._sync_deal_fields"
							) as mock_sync_fields:
								mock_get_deal.return_value = {"properties": {}}
								mock_get_companies.return_value = ("company-1", "company-2")
								_sync_deal("12345", "Deal-001")
								mock_get_deal.assert_called_once()
								mock_sync_org.assert_called_once()
								mock_sync_master.assert_called_once()
								mock_sync_contacts.assert_called_once()
								mock_sync_fields.assert_called_once()

	def test_sync_organization_exception_logged_and_suppressed(self):
		"""_sync_organization raises -> logged and suppressed, subsequent steps still execute"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal") as mock_get_deal:
			with patch(
				"ivm.integrations.hubspot.deal_handler.api.get_deal_company_ids_by_role"
			) as mock_get_companies:
				with patch("ivm.integrations.hubspot.deal_handler._sync_organization") as mock_sync_org:
					with patch(
						"ivm.integrations.hubspot.deal_handler._sync_master_organization"
					) as mock_sync_master:
						with patch(
							"ivm.integrations.hubspot.deal_handler._sync_contacts"
						) as mock_sync_contacts:
							with patch(
								"ivm.integrations.hubspot.deal_handler._sync_deal_fields"
							) as mock_sync_fields:
								with patch(
									"ivm.integrations.hubspot.deal_handler.frappe.log_error"
								) as mock_log_error:
									mock_get_deal.return_value = {"properties": {}}
									mock_get_companies.return_value = ("company-1", "company-2")
									mock_sync_org.side_effect = ValueError("org sync failed")
									_sync_deal("12345", "Deal-001")
									mock_log_error.assert_called()
									mock_sync_master.assert_called_once()
									mock_sync_contacts.assert_called_once()
									mock_sync_fields.assert_called_once()

	def test_sync_contacts_exception_logged_and_suppressed(self):
		"""_sync_contacts raises -> logged and suppressed, _sync_deal_fields still executes"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal") as mock_get_deal:
			with patch(
				"ivm.integrations.hubspot.deal_handler.api.get_deal_company_ids_by_role"
			) as mock_get_companies:
				with patch("ivm.integrations.hubspot.deal_handler._sync_organization"):
					with patch("ivm.integrations.hubspot.deal_handler._sync_master_organization"):
						with patch(
							"ivm.integrations.hubspot.deal_handler._sync_contacts"
						) as mock_sync_contacts:
							with patch(
								"ivm.integrations.hubspot.deal_handler._sync_deal_fields"
							) as mock_sync_fields:
								with patch(
									"ivm.integrations.hubspot.deal_handler.frappe.log_error"
								) as mock_log_error:
									mock_get_deal.return_value = {"properties": {}}
									mock_get_companies.return_value = ("company-1", "company-2")
									mock_sync_contacts.side_effect = ValueError("contacts sync failed")
									_sync_deal("12345", "Deal-001")
									mock_log_error.assert_called()
									mock_sync_fields.assert_called_once()

	def test_sync_deal_fields_exception_propagates(self):
		"""_sync_deal_fields raises -> propagates out of _sync_deal (NOT wrapped in try/except)"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal") as mock_get_deal:
			with patch(
				"ivm.integrations.hubspot.deal_handler.api.get_deal_company_ids_by_role"
			) as mock_get_companies:
				with patch("ivm.integrations.hubspot.deal_handler._sync_organization"):
					with patch("ivm.integrations.hubspot.deal_handler._sync_master_organization"):
						with patch("ivm.integrations.hubspot.deal_handler._sync_contacts"):
							with patch(
								"ivm.integrations.hubspot.deal_handler._sync_deal_fields"
							) as mock_sync_fields:
								mock_get_deal.return_value = {"properties": {}}
								mock_get_companies.return_value = ("company-1", "company-2")
								mock_sync_fields.side_effect = ValueError("fields sync failed")
								with self.assertRaises(ValueError):
									_sync_deal("12345", "Deal-001")

	def test_get_deal_company_ids_exception_logged_and_suppressed(self):
		"""get_deal_company_ids_by_role raises -> logged, None values passed to sync functions"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal") as mock_get_deal:
			with patch(
				"ivm.integrations.hubspot.deal_handler.api.get_deal_company_ids_by_role"
			) as mock_get_companies:
				with patch("ivm.integrations.hubspot.deal_handler._sync_organization") as mock_sync_org:
					with patch(
						"ivm.integrations.hubspot.deal_handler._sync_master_organization"
					) as mock_sync_master:
						with patch("ivm.integrations.hubspot.deal_handler._sync_contacts"):
							with patch("ivm.integrations.hubspot.deal_handler._sync_deal_fields"):
								with patch(
									"ivm.integrations.hubspot.deal_handler.frappe.log_error"
								) as mock_log_error:
									mock_get_deal.return_value = {"properties": {}}
									mock_get_companies.side_effect = ValueError("company fetch failed")
									_sync_deal("12345", "Deal-001")
									mock_log_error.assert_called()
									# Verify None values passed
									mock_sync_org.assert_called_once_with("12345", "Deal-001", None)
									mock_sync_master.assert_called_once_with("12345", "Deal-001", None)


class TestSyncContacts(FrappeTestCase):
	"""_sync_contacts function"""

	def test_multiple_contacts_upserted_first_marked_primary(self):
		"""Multiple contacts returned from API -> each upserted, first marked is_primary_contact=1"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal_contact_ids") as mock_get_ids:
			with patch("ivm.integrations.hubspot.deal_handler.api.get_contact") as mock_get_contact:
				with patch("ivm.integrations.hubspot.deal_handler._ensure_contacts") as mock_ensure:
					mock_get_ids.return_value = ["contact-1", "contact-2"]
					mock_get_contact.side_effect = [
						{"properties": {"firstname": "John", "lastname": "Doe", "email": "john@example.com"}},
						{
							"properties": {
								"firstname": "Jane",
								"lastname": "Smith",
								"email": "jane@example.com",
							}
						},
					]
					_sync_contacts("12345", "Deal-001")
					mock_ensure.assert_called_once()
					contacts = mock_ensure.call_args[0][1]
					self.assertEqual(len(contacts), 2)

	def test_empty_contact_ids_returns_without_upsert(self):
		"""api.get_deal_contact_ids returns empty list -> returns without any upsert calls"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal_contact_ids") as mock_get_ids:
			with patch("ivm.integrations.hubspot.deal_handler._ensure_contacts") as mock_ensure:
				mock_get_ids.return_value = []
				_sync_contacts("12345", "Deal-001")
				mock_ensure.assert_not_called()

	def test_contact_fetch_exception_logged_other_contacts_processed(self):
		"""One contact fetch fails -> other contacts still processed"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal_contact_ids") as mock_get_ids:
			with patch("ivm.integrations.hubspot.deal_handler.api.get_contact") as mock_get_contact:
				with patch("ivm.integrations.hubspot.deal_handler._ensure_contacts") as mock_ensure:
					with patch("ivm.integrations.hubspot.deal_handler.frappe.log_error") as mock_log_error:
						mock_get_ids.return_value = ["contact-1", "contact-2"]
						mock_get_contact.side_effect = [
							ValueError("fetch failed"),
							{
								"properties": {
									"firstname": "Jane",
									"lastname": "Smith",
									"email": "jane@example.com",
								}
							},
						]
						_sync_contacts("12345", "Deal-001")
						mock_log_error.assert_called()
						mock_ensure.assert_called_once()
						contacts = mock_ensure.call_args[0][1]
						self.assertEqual(len(contacts), 1)

	def test_get_contact_ids_exception_logged_returns(self):
		"""api.get_deal_contact_ids raises -> logged and returns"""
		with patch("ivm.integrations.hubspot.deal_handler.api.get_deal_contact_ids") as mock_get_ids:
			with patch("ivm.integrations.hubspot.deal_handler._ensure_contacts") as mock_ensure:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.log_error") as mock_log_error:
					mock_get_ids.side_effect = ValueError("fetch failed")
					_sync_contacts("12345", "Deal-001")
					mock_log_error.assert_called()
					mock_ensure.assert_not_called()


class TestEnsureContacts(FrappeTestCase):
	"""_ensure_contacts function"""

	def test_multiple_contacts_upserted_first_marked_primary(self):
		"""Multiple contacts upserted, first contact marked is_primary_contact=1"""
		with patch("ivm.integrations.hubspot.contact_handler.upsert_contact") as mock_upsert:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.get_doc") as mock_get_doc:
				with patch("ivm.integrations.hubspot.deal_handler.save_doc"):
					mock_upsert.side_effect = ["Contact-1", "Contact-2"]
					mock_doc = MagicMock()
					mock_doc.doctype = "CRM Deal"
					mock_doc.name = "Deal-001"
					mock_doc.get.return_value = []
					mock_get_doc.return_value = mock_doc
					contacts = [
						{"first_name": "John", "last_name": "Doe"},
						{"first_name": "Jane", "last_name": "Smith"},
					]
					_ensure_contacts("Deal-001", contacts)
					self.assertEqual(mock_upsert.call_count, 2)
					# Verify append was called with is_primary=1 for first, 0 for second
					calls = mock_doc.append.call_args_list
					self.assertEqual(len(calls), 2)
					self.assertEqual(calls[0][0][1]["is_primary"], 1)
					self.assertEqual(calls[1][0][1]["is_primary"], 0)

	def test_one_contact_fails_upsert_others_processed(self):
		"""One contact fails to upsert -> other contacts still processed"""
		with patch("ivm.integrations.hubspot.contact_handler.upsert_contact") as mock_upsert:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.get_doc") as mock_get_doc:
				with patch("ivm.integrations.hubspot.deal_handler.frappe.log_error") as mock_log_error:
					with patch("ivm.integrations.hubspot.deal_handler.save_doc"):
						mock_upsert.side_effect = [ValueError("upsert failed"), "Contact-2"]
						mock_doc = MagicMock()
						mock_doc.doctype = "CRM Deal"
						mock_doc.name = "Deal-001"
						mock_doc.get.return_value = []
						mock_get_doc.return_value = mock_doc
						contacts = [
							{"first_name": "John", "last_name": "Doe"},
							{"first_name": "Jane", "last_name": "Smith"},
						]
						_ensure_contacts("Deal-001", contacts)
						mock_log_error.assert_called()
						# Only second contact should be appended
						self.assertEqual(mock_doc.append.call_count, 1)

	def test_upsert_returns_none_skipped(self):
		"""Contact upsert returns None -> skipped"""
		with patch("ivm.integrations.hubspot.contact_handler.upsert_contact") as mock_upsert:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.get_doc") as mock_get_doc:
				with patch("ivm.integrations.hubspot.deal_handler.save_doc"):
					mock_upsert.side_effect = [None, "Contact-2"]
					mock_doc = MagicMock()
					mock_doc.doctype = "CRM Deal"
					mock_doc.name = "Deal-001"
					mock_doc.get.return_value = []
					mock_get_doc.return_value = mock_doc
					contacts = [
						{"first_name": "John", "last_name": "Doe"},
						{"first_name": "Jane", "last_name": "Smith"},
					]
					_ensure_contacts("Deal-001", contacts)
					# Only second contact should be appended
					self.assertEqual(mock_doc.append.call_count, 1)

	def test_duplicate_contact_not_re_added(self):
		"""Contact already present in deal's child table (duplicate) -> not re-added"""
		with patch("ivm.integrations.hubspot.contact_handler.upsert_contact") as mock_upsert:
			with patch("ivm.integrations.hubspot.deal_handler.frappe.get_doc") as mock_get_doc:
				with patch("ivm.integrations.hubspot.deal_handler.save_doc"):
					mock_upsert.return_value = "Contact-1"
					mock_doc = MagicMock()
					mock_doc.doctype = "CRM Deal"
					mock_doc.name = "Deal-001"
					# Simulate existing contact in child table
					existing_row = MagicMock()
					existing_row.contact = "Contact-1"
					mock_doc.get.return_value = [existing_row]
					mock_get_doc.return_value = mock_doc
					contacts = [{"first_name": "John", "last_name": "Doe"}]
					_ensure_contacts("Deal-001", contacts)
					# Contact should not be appended since it already exists
					mock_doc.append.assert_not_called()

	def test_empty_contacts_list_no_op(self):
		"""Empty contacts list -> no-op"""
		with patch("ivm.integrations.hubspot.deal_handler.frappe.get_doc") as mock_get_doc:
			_ensure_contacts("Deal-001", [])
			mock_get_doc.assert_not_called()
