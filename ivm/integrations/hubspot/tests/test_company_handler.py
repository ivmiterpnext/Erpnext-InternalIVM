"""Tests for ivm.integrations.hubspot.company_handler"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.company_handler import (
	_apply_annual_revenue,
	_apply_employee_count,
	_apply_industry,
	_maybe_rename_org,
	_sync_company,
	_sync_org_address,
	handle_company_created,
	handle_company_updated,
)
from ivm.integrations.hubspot.constants import HUBSPOT_COMPANY_ID_FIELD
from ivm.integrations.hubspot.sync_utils import ConcurrentCreateConflict


class TestApplyEmployeeCount(FrappeTestCase):
	"""_apply_employee_count field transform"""

	def test_numeric_string_buckets_to_range(self):
		"""Numeric string '150' buckets to '51-200' range."""
		doc = SimpleNamespace()
		_apply_employee_count(doc, "150")
		self.assertEqual(doc.no_of_employees, "51-200")

	def test_zero_does_not_set_field(self):
		"""Zero value does not set no_of_employees."""
		doc = SimpleNamespace()
		_apply_employee_count(doc, "0")
		self.assertFalse(hasattr(doc, "no_of_employees"))

	def test_non_numeric_does_not_set_field(self):
		"""Non-numeric value does not set no_of_employees."""
		doc = SimpleNamespace()
		_apply_employee_count(doc, "abc")
		self.assertFalse(hasattr(doc, "no_of_employees"))

	def test_none_does_not_set_field(self):
		"""None value does not set no_of_employees."""
		doc = SimpleNamespace()
		_apply_employee_count(doc, None)
		self.assertFalse(hasattr(doc, "no_of_employees"))


class TestApplyAnnualRevenue(FrappeTestCase):
	"""_apply_annual_revenue field transform"""

	def test_numeric_string_coerced_to_float(self):
		"""Numeric string '5000000' coerced to 5000000.0."""
		doc = SimpleNamespace()
		_apply_annual_revenue(doc, "5000000")
		self.assertEqual(doc.annual_revenue, 5000000.0)

	def test_none_does_not_set_field(self):
		"""None value does not set annual_revenue."""
		doc = SimpleNamespace()
		_apply_annual_revenue(doc, None)
		self.assertFalse(hasattr(doc, "annual_revenue"))

	def test_empty_string_does_not_set_field(self):
		"""Empty string does not set annual_revenue."""
		doc = SimpleNamespace()
		_apply_annual_revenue(doc, "")
		self.assertFalse(hasattr(doc, "annual_revenue"))


class TestApplyIndustry(FrappeTestCase):
	"""_apply_industry field transform"""

	def test_known_industry_key_maps_to_label(self):
		"""Known HubSpot industry key maps to CRM Industry label."""
		doc = SimpleNamespace()
		_apply_industry(doc, "ACCOUNTING")
		self.assertEqual(doc.industry, "Accounting")

	def test_unknown_industry_key_logs_debug_and_does_not_set(self):
		"""Unknown industry key logs debug message and does not set field."""
		doc = SimpleNamespace()
		with patch("ivm.integrations.hubspot.company_handler.frappe.logger") as mock_logger:
			_apply_industry(doc, "UNKNOWN_INDUSTRY")
			mock_logger.assert_called_once()
			self.assertFalse(hasattr(doc, "industry"))

	def test_none_does_not_set_field(self):
		"""None value does not set industry."""
		doc = SimpleNamespace()
		_apply_industry(doc, None)
		self.assertFalse(hasattr(doc, "industry"))

	def test_empty_string_does_not_set_field(self):
		"""Empty string does not set industry."""
		doc = SimpleNamespace()
		_apply_industry(doc, "")
		self.assertFalse(hasattr(doc, "industry"))


class TestHandleCompanyCreated(FrappeTestCase):
	"""handle_company_created entry point"""

	def test_new_company_creates_and_syncs(self):
		"""New company creates via lookup_or_create and calls _sync_company."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler._sync_company") as mock_sync:
				with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
					mock_lookup.return_value = (MagicMock(name="Test Org"), True)
					handle_company_created(hubspot_company_id="123")
					mock_lookup.assert_called_once()
					mock_sync.assert_called_once()

	def test_duplicate_company_logs_and_returns_without_syncing(self):
		"""Duplicate (is_new=False) logs info and returns without syncing."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler._sync_company") as mock_sync:
				with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
					with patch("ivm.integrations.hubspot.company_handler.frappe.logger") as mock_logger:
						mock_lookup.return_value = (MagicMock(name="Existing Org"), False)
						handle_company_created(hubspot_company_id="456")
						mock_logger.assert_called_once()
						mock_sync.assert_not_called()

	def test_concurrent_create_conflict_re_enqueues(self):
		"""ConcurrentCreateConflict raised internally re-enqueues via decorator."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
				with patch("ivm.integrations.hubspot.company_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.company_handler.frappe.logger"):
						mock_lookup.side_effect = ConcurrentCreateConflict(
							"CRM Organization", HUBSPOT_COMPANY_ID_FIELD, "789"
						)
						result = handle_company_created(hubspot_company_id="789")
						self.assertIsNone(result)
						mock_enqueue.assert_called_once()

	def test_hubspot_rate_limit_exhausted_re_enqueues(self):
		"""HubSpotRateLimitExhausted raised internally re-enqueues via decorator."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
				with patch("ivm.integrations.hubspot.company_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.company_handler.frappe.logger"):
						mock_lookup.side_effect = api.HubSpotRateLimitExhausted(retry_after_seconds=10.0)
						result = handle_company_created(hubspot_company_id="999")
						self.assertIsNone(result)
						mock_enqueue.assert_called_once()

	def test_generic_exception_logs_error_and_does_not_propagate(self):
		"""Generic Exception logs error via frappe.log_error and does not propagate."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
				with patch("ivm.integrations.hubspot.company_handler.frappe.log_error") as mock_log_error:
					with patch("ivm.integrations.hubspot.company_handler.frappe.get_traceback"):
						mock_lookup.side_effect = ValueError("test error")
						handle_company_created(hubspot_company_id="111")
						mock_log_error.assert_called_once()


class TestHandleCompanyUpdated(FrappeTestCase):
	"""handle_company_updated entry point"""

	def test_existing_org_found_calls_sync_company(self):
		"""Existing org found calls _sync_company."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler._sync_company") as mock_sync:
				with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
					mock_get_value.return_value = "Existing Org"
					handle_company_updated(hubspot_company_id="123")
					mock_sync.assert_called_once_with("123", "Existing Org")

	def test_org_not_found_calls_handle_company_created(self):
		"""Org not found falls through and calls handle_company_created."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
				with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
					with patch("ivm.integrations.hubspot.company_handler.frappe.logger"):
						mock_get_value.return_value = None
						handle_company_updated(hubspot_company_id="456", hubspot_user_id="user123")
						mock_create.assert_called_once_with("456", "user123")

	def test_hubspot_rate_limit_exhausted_re_enqueues(self):
		"""HubSpotRateLimitExhausted raised internally re-enqueues via decorator."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
				with patch("ivm.integrations.hubspot.company_handler.frappe.enqueue") as mock_enqueue:
					with patch("ivm.integrations.hubspot.company_handler.frappe.logger"):
						mock_get_value.side_effect = api.HubSpotRateLimitExhausted(retry_after_seconds=10.0)
						result = handle_company_updated(hubspot_company_id="789")
						self.assertIsNone(result)
						mock_enqueue.assert_called_once()

	def test_generic_exception_logs_error_and_does_not_propagate(self):
		"""Generic Exception logs error via frappe.log_error and does not propagate."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.company_handler.set_acting_user"):
				with patch("ivm.integrations.hubspot.company_handler.frappe.log_error") as mock_log_error:
					with patch("ivm.integrations.hubspot.company_handler.frappe.get_traceback"):
						mock_get_value.side_effect = RuntimeError("test error")
						handle_company_updated(hubspot_company_id="999")
						mock_log_error.assert_called_once()


class TestMaybeRenameOrg(FrappeTestCase):
	"""_maybe_rename_org helper"""

	def test_org_name_starts_with_hs_and_new_name_available_renames(self):
		"""Org name starts with 'HS-' and new name available renames via frappe.rename_doc."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.exists") as mock_exists:
			with patch("ivm.integrations.hubspot.company_handler.frappe.rename_doc") as mock_rename:
				with patch("ivm.integrations.hubspot.company_handler.frappe.logger"):
					mock_exists.return_value = False
					result = _maybe_rename_org("HS-123", {"name": "Acme Corp"})
					mock_rename.assert_called_once_with("CRM Organization", "HS-123", "Acme Corp", force=True)
					self.assertEqual(result, "Acme Corp")

	def test_org_name_does_not_start_with_hs_no_rename_attempted(self):
		"""Org name does NOT start with 'HS-' no rename attempted."""
		result = _maybe_rename_org("Real Name", {"name": "New Name"})
		self.assertEqual(result, "Real Name")

	def test_target_name_already_exists_logs_warning_and_returns_original(self):
		"""Target name already exists logs warning and returns original name."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.exists") as mock_exists:
			with patch("ivm.integrations.hubspot.company_handler.frappe.logger") as mock_logger:
				mock_exists.return_value = True
				result = _maybe_rename_org("HS-123", {"name": "Existing Name"})
				mock_logger.assert_called_once()
				self.assertEqual(result, "HS-123")

	def test_frappe_rename_doc_raises_exception_logs_warning_and_returns_original(self):
		"""frappe.rename_doc raises exception logs warning and returns original name."""
		with patch("ivm.integrations.hubspot.company_handler.frappe.db.exists") as mock_exists:
			with patch("ivm.integrations.hubspot.company_handler.frappe.rename_doc") as mock_rename:
				with patch("ivm.integrations.hubspot.company_handler.frappe.logger") as mock_logger:
					mock_exists.return_value = False
					mock_rename.side_effect = Exception("rename failed")
					result = _maybe_rename_org("HS-123", {"name": "New Name"})
					mock_logger.assert_called_once()
					self.assertEqual(result, "HS-123")

	def test_no_new_name_in_properties_returns_original(self):
		"""No new name in properties returns original name unchanged."""
		result = _maybe_rename_org("HS-123", {})
		self.assertEqual(result, "HS-123")

	def test_empty_new_name_in_properties_returns_original(self):
		"""Empty new name in properties returns original name unchanged."""
		result = _maybe_rename_org("HS-123", {"name": ""})
		self.assertEqual(result, "HS-123")


class TestSyncOrgAddress(FrappeTestCase):
	"""_sync_org_address helper"""

	def test_calls_upsert_address_with_correct_kwargs(self):
		"""Calls upsert_address with correct kwargs derived from properties dict."""
		with patch("ivm.integrations.hubspot.company_handler.upsert_address") as mock_upsert:
			properties = {
				"address": "123 Main St",
				"city": "Springfield",
				"state": "IL",
				"country": "USA",
				"zip": "62701",
			}
			_sync_org_address("Test Org", properties)
			mock_upsert.assert_called_once_with(
				address_line1="123 Main St",
				city="Springfield",
				state="IL",
				country="USA",
				pincode="62701",
				link_doctype="CRM Organization",
				link_name="Test Org",
			)

	def test_handles_missing_address_fields(self):
		"""Handles missing address fields gracefully."""
		with patch("ivm.integrations.hubspot.company_handler.upsert_address") as mock_upsert:
			properties = {"city": "Springfield"}
			_sync_org_address("Test Org", properties)
			mock_upsert.assert_called_once_with(
				address_line1="",
				city="Springfield",
				state="",
				country="",
				pincode="",
				link_doctype="CRM Organization",
				link_name="Test Org",
			)


class TestSyncCompany(FrappeTestCase):
	"""_sync_company helper"""

	def test_fetches_company_and_applies_field_map_and_address(self):
		"""Fetches company properties, applies field map, and syncs address."""
		with patch("ivm.integrations.hubspot.company_handler.api.get_company") as mock_get:
			with patch("ivm.integrations.hubspot.company_handler.apply_field_map") as mock_apply:
				with patch("ivm.integrations.hubspot.company_handler.save_doc") as mock_save:
					with patch("ivm.integrations.hubspot.company_handler._maybe_rename_org") as mock_rename:
						with patch("ivm.integrations.hubspot.company_handler._sync_org_address") as mock_addr:
							with patch(
								"ivm.integrations.hubspot.company_handler.frappe.get_doc"
							) as mock_get_doc:
								mock_get.return_value = {
									"properties": {
										"name": "Acme Corp",
										"website": "https://acme.com",
									}
								}
								mock_rename.return_value = "Acme Corp"
								mock_doc = MagicMock()
								mock_get_doc.return_value = mock_doc

								_sync_company("123", "HS-123")

								mock_get.assert_called_once()
								mock_apply.assert_called_once()
								mock_save.assert_called_once()
								mock_addr.assert_called_once()
