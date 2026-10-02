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
	_sync_company_core,
	_sync_org_address,
	sync_company,
)
from ivm.integrations.hubspot.constants import COMPANY_TYPE_ID, HUBSPOT_COMPANY_ID_FIELD
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


class TestSyncCompanyCore(FrappeTestCase):
	"""_sync_company_core function"""

	def test_creates_and_syncs(self):
		"""Creates org via lookup_or_create and calls _sync_company."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler._sync_company") as mock_sync:
				mock_doc = MagicMock()
				mock_doc.name = "Test Org"
				mock_lookup.return_value = (mock_doc, True)
				mock_sync.return_value = "Test Org"
				result = _sync_company_core("123")
				self.assertEqual(result, "Test Org")
				mock_lookup.assert_called_once()
				mock_sync.assert_called_once_with("123", "Test Org")

	def test_always_resyncs_existing_org(self):
		"""Even if org already existed (is_new=False), _sync_company is still called."""
		with patch("ivm.integrations.hubspot.company_handler.lookup_or_create") as mock_lookup:
			with patch("ivm.integrations.hubspot.company_handler._sync_company") as mock_sync:
				mock_doc = MagicMock()
				mock_doc.name = "Existing Org"
				mock_lookup.return_value = (mock_doc, False)  # is_new=False
				mock_sync.return_value = "Existing Org"
				result = _sync_company_core("456")
				self.assertEqual(result, "Existing Org")
				mock_sync.assert_called_once_with("456", "Existing Org")


class TestSyncCompanyEntry(FrappeTestCase):
	"""sync_company entry point (decorated with @retry_via_reenqueue)"""

	def test_calls_core_with_set_acting_user(self):
		"""sync_company calls set_acting_user and _sync_company_core."""
		with patch("ivm.integrations.hubspot.company_handler.set_acting_user") as mock_set_user:
			with patch("ivm.integrations.hubspot.company_handler._sync_company_core") as mock_core:
				sync_company(hubspot_company_id="789")
				mock_set_user.assert_called_once_with()
				mock_core.assert_called_once_with("789")


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
