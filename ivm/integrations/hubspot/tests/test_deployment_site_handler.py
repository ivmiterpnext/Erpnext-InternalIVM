"""Tests for ivm.integrations.hubspot.deployment_site_handler"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.deployment_site_handler import (
	_map_properties,
	_resolve_deal_for_site,
	_upsert_location_from_webhook,
	handle_bin_webhook,
	handle_machine_webhook,
	handle_site_webhook,
)


class TestMapProperties(FrappeTestCase):
	"""_map_properties field mapping function"""

	def test_maps_hubspot_keys_to_frappe_fields(self):
		"""HubSpot properties mapped to Frappe fields via field_map"""
		field_map = {"hs_key_1": "frappe_field_1", "hs_key_2": "frappe_field_2"}
		properties = {"hs_key_1": "value1", "hs_key_2": "value2"}
		result = _map_properties(properties, field_map)
		self.assertEqual(result, {"frappe_field_1": "value1", "frappe_field_2": "value2"})

	def test_skips_none_values(self):
		"""None values in properties are skipped"""
		field_map = {"hs_key_1": "frappe_field_1", "hs_key_2": "frappe_field_2"}
		properties = {"hs_key_1": "value1", "hs_key_2": None}
		result = _map_properties(properties, field_map)
		self.assertEqual(result, {"frappe_field_1": "value1"})

	def test_skips_empty_string_values(self):
		"""Empty string values in properties are skipped"""
		field_map = {"hs_key_1": "frappe_field_1", "hs_key_2": "frappe_field_2"}
		properties = {"hs_key_1": "value1", "hs_key_2": ""}
		result = _map_properties(properties, field_map)
		self.assertEqual(result, {"frappe_field_1": "value1"})

	def test_skips_unmapped_keys(self):
		"""Keys not in field_map are skipped"""
		field_map = {"hs_key_1": "frappe_field_1"}
		properties = {"hs_key_1": "value1", "hs_key_2": "value2"}
		result = _map_properties(properties, field_map)
		self.assertEqual(result, {"frappe_field_1": "value1"})

	def test_coerces_values_with_meta(self):
		"""Values coerced via coerce_value when meta provided"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.coerce_value") as mock_coerce:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.get_meta") as mock_get_meta:
				mock_meta = MagicMock()
				mock_field = MagicMock()
				mock_meta.get_field.return_value = mock_field
				mock_get_meta.return_value = mock_meta
				mock_coerce.return_value = "coerced_value"

				field_map = {"hs_key_1": "frappe_field_1"}
				properties = {"hs_key_1": "raw_value"}
				result = _map_properties(properties, field_map, mock_meta)

				mock_coerce.assert_called_once_with("raw_value", mock_field)
				self.assertEqual(result, {"frappe_field_1": "coerced_value"})

	def test_coerces_without_meta(self):
		"""Values coerced with None field when meta not provided"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.coerce_value") as mock_coerce:
			mock_coerce.return_value = "coerced_value"

			field_map = {"hs_key_1": "frappe_field_1"}
			properties = {"hs_key_1": "raw_value"}
			result = _map_properties(properties, field_map, None)

			mock_coerce.assert_called_once_with("raw_value", None)
			self.assertEqual(result, {"frappe_field_1": "coerced_value"})


class TestResolveDealForSite(FrappeTestCase):
	"""_resolve_deal_for_site deal resolution function"""

	def test_returns_existing_deal_when_found_by_hubspot_id(self):
		"""Site has deal association and deal exists locally -> returns deal name"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_site_deal_ids") as mock_get_ids:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value"
			) as mock_get_value:
				mock_get_ids.return_value = ["deal-123"]
				mock_get_value.return_value = "Deal-001"

				result = _resolve_deal_for_site("site-456")

				self.assertEqual(result, "Deal-001")
				mock_get_ids.assert_called_once_with("site-456")

	def test_self_heals_by_creating_deal_when_hubspot_id_not_local(self):
		"""Site has deal association but deal not local -> creates via ensure_deal_exists"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_site_deal_ids") as mock_get_ids:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value"
			) as mock_get_value:
				with patch("ivm.integrations.hubspot.deal_handler.ensure_deal_exists") as mock_ensure:
					mock_get_ids.return_value = ["deal-123"]
					mock_get_value.return_value = None
					mock_ensure.return_value = ("Deal-001", True)

					result = _resolve_deal_for_site("site-456", hubspot_user_id="user-789")

					self.assertEqual(result, "Deal-001")
					mock_ensure.assert_called_once_with("deal-123", "user-789")

	def test_falls_back_to_local_deployment_location_when_no_hubspot_association(self):
		"""No HubSpot deal association but local Deployment Location exists -> returns its deal"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_site_deal_ids") as mock_get_ids:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value"
			) as mock_get_value:
				mock_get_ids.return_value = []
				# Only one call to get_value for the local fallback (no HubSpot loop)
				mock_get_value.return_value = "Deal-002"

				result = _resolve_deal_for_site("site-456")

				self.assertEqual(result, "Deal-002")

	def test_returns_none_and_logs_when_no_deal_found(self):
		"""No deal found anywhere -> logs warning and returns None"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_site_deal_ids") as mock_get_ids:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value"
			) as mock_get_value:
				with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger") as mock_logger:
					mock_get_ids.return_value = []
					mock_get_value.return_value = None

					result = _resolve_deal_for_site("site-456")

					self.assertIsNone(result)
					mock_logger.assert_called()

	def test_api_exception_logged_and_suppressed(self):
		"""api.get_site_deal_ids raises -> logged and suppressed, returns None"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_site_deal_ids") as mock_get_ids:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.log_error") as mock_log_error:
				mock_get_ids.side_effect = ValueError("API error")

				result = _resolve_deal_for_site("site-456")

				self.assertIsNone(result)
				mock_log_error.assert_called()

	def test_hubspot_rate_limit_re_raises(self):
		"""api.HubSpotRateLimitExhausted raised -> re-raised (not suppressed)"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_site_deal_ids") as mock_get_ids:
			mock_get_ids.side_effect = api.HubSpotRateLimitExhausted(retry_after_seconds=60)

			with self.assertRaises(api.HubSpotRateLimitExhausted):
				_resolve_deal_for_site("site-456")


class TestUpsertLocationFromWebhook(FrappeTestCase):
	"""_upsert_location_from_webhook create/update function"""

	def test_updates_existing_location_by_hubspot_site_id(self):
		"""Existing Deployment Location found -> loads and updates it"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.get_doc") as mock_get_doc:
				with patch("ivm.integrations.hubspot.deployment_site_handler._apply_site_properties"):
					with patch("ivm.integrations.hubspot.deployment_site_handler._apply_machine_data"):
						mock_get_value.return_value = "Location-001"
						mock_doc = MagicMock()
						mock_doc.doctype = "Deployment Location"
						mock_doc.name = "Location-001"
						mock_doc.location_name = "Existing Site"
						mock_get_doc.return_value = mock_doc

						_upsert_location_from_webhook(
							"Deal-001",
							"site-456",
							{"site_location_name": "Site Name"},
							{},
						)

						mock_get_doc.assert_called_once_with("Deployment Location", "Location-001")
						mock_doc.save.assert_called_once_with(ignore_permissions=True)
						mock_doc.insert.assert_not_called()

	def test_creates_new_location_when_not_found(self):
		"""No existing Deployment Location -> creates new one"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.new_doc") as mock_new_doc:
				with patch("ivm.integrations.hubspot.deployment_site_handler._apply_site_properties"):
					with patch("ivm.integrations.hubspot.deployment_site_handler._apply_machine_data"):
						mock_get_value.return_value = None
						mock_doc = MagicMock()
						mock_doc.doctype = "Deployment Location"
						mock_doc.name = "Location-002"
						mock_doc.location_name = None
						mock_new_doc.return_value = mock_doc

						_upsert_location_from_webhook(
							"Deal-001",
							"site-456",
							{"site_location_name": "Site Name"},
							{},
						)

						mock_new_doc.assert_called_once_with("Deployment Location")
						self.assertEqual(mock_doc.crm_deal, "Deal-001")
						self.assertEqual(mock_doc.hubspot_site_id, "site-456")
						mock_doc.insert.assert_called_once_with(ignore_permissions=True)
						mock_doc.save.assert_not_called()

	def test_sets_default_location_name_when_empty(self):
		"""Empty location_name -> derives default name from site ID"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.new_doc") as mock_new_doc:
				with patch("ivm.integrations.hubspot.deployment_site_handler._apply_site_properties"):
					with patch("ivm.integrations.hubspot.deployment_site_handler._apply_machine_data"):
						mock_get_value.return_value = None
						mock_doc = MagicMock()
						mock_doc.doctype = "Deployment Location"
						mock_doc.name = "Location-002"
						mock_doc.location_name = None
						mock_new_doc.return_value = mock_doc

						_upsert_location_from_webhook(
							"Deal-001",
							"site-456",
							{},
							{},
						)

						self.assertEqual(mock_doc.location_name, "Site site-456")

	def test_applies_site_properties_and_machine_data(self):
		"""Site properties and machine data applied to location"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.new_doc") as mock_new_doc:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._apply_site_properties"
				) as mock_apply_props:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler._apply_machine_data"
					) as mock_apply_machines:
						mock_get_value.return_value = None
						mock_doc = MagicMock()
						mock_doc.doctype = "Deployment Location"
						mock_doc.name = "Location-002"
						mock_doc.location_name = "Site Name"
						mock_new_doc.return_value = mock_doc

						site_props = {"site_location_name": "Site Name"}
						machines = {"smartstation_details": [{"machine_name": "SS-001"}]}

						_upsert_location_from_webhook(
							"Deal-001",
							"site-456",
							site_props,
							machines,
						)

						mock_apply_props.assert_called_once_with(mock_doc, site_props)
						mock_apply_machines.assert_called_once_with(mock_doc, machines)


class TestHandleSiteWebhook(FrappeTestCase):
	"""handle_site_webhook webhook handler"""

	def test_syncs_site_when_deal_found(self):
		"""Site linked to existing deal -> fetches and upserts location"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"
			) as mock_resolve:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object"
				) as mock_get_obj:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler._fetch_site_machines"
					) as mock_fetch_machines:
						with patch(
							"ivm.integrations.hubspot.deployment_site_handler._upsert_location_from_webhook"
						) as mock_upsert:
							with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
								mock_resolve.return_value = "Deal-001"
								mock_get_obj.return_value = {"properties": {"site_location_name": "Site A"}}
								mock_fetch_machines.return_value = {}

								handle_site_webhook(hubspot_site_id="site-456")

								mock_resolve.assert_called_once_with("site-456", None)
								mock_get_obj.assert_called_once()
								mock_fetch_machines.assert_called_once_with("site-456")
								mock_upsert.assert_called_once()

	def test_returns_without_action_when_no_deal_found(self):
		"""Site with no deal association -> returns without upsert"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"
			) as mock_resolve:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object"
				) as mock_get_obj:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler._upsert_location_from_webhook"
					) as mock_upsert:
						mock_resolve.return_value = None

						handle_site_webhook(hubspot_site_id="site-456")

						mock_get_obj.assert_not_called()
						mock_upsert.assert_not_called()

	def test_rate_limit_exception_re_raises(self):
		"""api.HubSpotRateLimitExhausted raised inside _log_error -> re-raises (not suppressed)"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"
			) as mock_resolve:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object"
				) as mock_get_obj:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.enqueue"
					) as mock_enqueue:
						mock_resolve.return_value = "Deal-001"
						mock_get_obj.side_effect = api.HubSpotRateLimitExhausted(retry_after_seconds=60)

						# Rate limit exception is re-raised by _log_error, caught by @retry_via_reenqueue decorator
						# which enqueues it instead of propagating
						handle_site_webhook(hubspot_site_id="site-456")
						mock_enqueue.assert_called_once()

	def test_generic_exception_logged_not_propagated(self):
		"""Generic Exception raised -> logged and suppressed"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"
			) as mock_resolve:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object"
				) as mock_get_obj:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.log_error"
					) as mock_log_error:
						with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.get_traceback"):
							mock_resolve.return_value = "Deal-001"
							mock_get_obj.side_effect = ValueError("fetch failed")

							# Should not raise
							handle_site_webhook(hubspot_site_id="site-456")

							mock_log_error.assert_called_once()

	def test_requires_keyword_only_args(self):
		"""handle_site_webhook requires keyword-only args (decorated with @retry_via_reenqueue)"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"):
				# Positional args should raise TypeError
				with self.assertRaises(TypeError):
					handle_site_webhook("site-456")


class TestHandleMachineWebhook(FrappeTestCase):
	"""handle_machine_webhook webhook handler"""

	def test_calls_handle_site_webhook_for_single_site(self):
		"""Machine linked to 1 site -> calls handle_site_webhook once"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_site_webhook"
				) as mock_handle_site:
					mock_get_sites.return_value = ["site-456"]

					handle_machine_webhook(
						machine_type_id="2-230236986",
						hubspot_machine_id="machine-123",
					)

					mock_handle_site.assert_called_once_with("site-456", hubspot_user_id=None)

	def test_calls_handle_site_webhook_for_multiple_sites(self):
		"""Machine linked to 2 sites -> calls handle_site_webhook twice"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_site_webhook"
				) as mock_handle_site:
					mock_get_sites.return_value = ["site-456", "site-789"]

					handle_machine_webhook(
						machine_type_id="2-230236986",
						hubspot_machine_id="machine-123",
						hubspot_user_id="user-999",
					)

					self.assertEqual(mock_handle_site.call_count, 2)
					calls = mock_handle_site.call_args_list
					self.assertEqual(calls[0][0][0], "site-456")
					self.assertEqual(calls[1][0][0], "site-789")
					self.assertEqual(calls[0][1]["hubspot_user_id"], "user-999")
					self.assertEqual(calls[1][1]["hubspot_user_id"], "user-999")

	def test_returns_without_action_when_get_machine_site_ids_returns_none(self):
		"""api.get_machine_site_ids returns None -> returns without action"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_site_webhook"
				) as mock_handle_site:
					mock_get_sites.return_value = None

					handle_machine_webhook(
						machine_type_id="2-230236986",
						hubspot_machine_id="machine-123",
					)

					mock_handle_site.assert_not_called()

	def test_logs_warning_and_returns_when_site_ids_empty(self):
		"""api.get_machine_site_ids returns empty list -> logs warning and returns"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_site_webhook"
				) as mock_handle_site:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.logger"
					) as mock_logger:
						mock_get_sites.return_value = []

						handle_machine_webhook(
							machine_type_id="2-230236986",
							hubspot_machine_id="machine-123",
						)

						mock_logger.assert_called()
						mock_handle_site.assert_not_called()

	def test_exception_in_get_machine_site_ids_logged_and_suppressed(self):
		"""api.get_machine_site_ids raises -> logged and suppressed"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_site_webhook"
				) as mock_handle_site:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.log_error"
					) as mock_log_error:
						mock_get_sites.side_effect = ValueError("fetch failed")

						handle_machine_webhook(
							machine_type_id="2-230236986",
							hubspot_machine_id="machine-123",
						)

						mock_log_error.assert_called()
						mock_handle_site.assert_not_called()

	def test_exception_in_handle_site_webhook_logged_and_suppressed(self):
		"""Exception in handle_site_webhook call -> logged and suppressed, other sites still processed"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_site_webhook"
				) as mock_handle_site:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.log_error"
					) as mock_log_error:
						mock_get_sites.return_value = ["site-456", "site-789"]
						mock_handle_site.side_effect = [ValueError("sync failed"), None]

						handle_machine_webhook(
							machine_type_id="2-230236986",
							hubspot_machine_id="machine-123",
						)

						mock_log_error.assert_called()
						self.assertEqual(mock_handle_site.call_count, 2)

	def test_requires_keyword_only_args(self):
		"""handle_machine_webhook requires keyword-only args (decorated with @retry_via_reenqueue)"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"):
				# Positional args should raise TypeError
				with self.assertRaises(TypeError):
					handle_machine_webhook("2-230236986", "machine-123")


class TestHandleBinWebhook(FrappeTestCase):
	"""handle_bin_webhook webhook handler"""

	def test_calls_handle_machine_webhook_for_single_machine(self):
		"""Bin linked to 1 machine -> calls handle_machine_webhook once"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_machine_webhook"
				) as mock_handle_machine:
					mock_get_machines.return_value = [("2-230363982", "machine-123")]

					handle_bin_webhook(hubspot_bin_id="bin-456")

					# handle_machine_webhook is called with positional args (machine_type_id, machine_id)
					mock_handle_machine.assert_called_once_with(
						"2-230363982",
						"machine-123",
						hubspot_user_id=None,
					)

	def test_calls_handle_machine_webhook_for_multiple_machines(self):
		"""Bin linked to 2 machines -> calls handle_machine_webhook twice"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_machine_webhook"
				) as mock_handle_machine:
					mock_get_machines.return_value = [
						("2-230363982", "machine-123"),
						("2-230364924", "machine-456"),
					]

					handle_bin_webhook(
						hubspot_bin_id="bin-789",
						hubspot_user_id="user-999",
					)

					self.assertEqual(mock_handle_machine.call_count, 2)
					calls = mock_handle_machine.call_args_list
					# Calls are with positional args (machine_type_id, machine_id) + keyword arg hubspot_user_id
					self.assertEqual(calls[0][0][0], "2-230363982")
					self.assertEqual(calls[0][0][1], "machine-123")
					self.assertEqual(calls[1][0][0], "2-230364924")
					self.assertEqual(calls[1][0][1], "machine-456")
					self.assertEqual(calls[0][1]["hubspot_user_id"], "user-999")
					self.assertEqual(calls[1][1]["hubspot_user_id"], "user-999")

	def test_returns_without_action_when_get_bin_machine_ids_returns_none(self):
		"""api.get_bin_machine_ids returns None -> returns without action"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_machine_webhook"
				) as mock_handle_machine:
					mock_get_machines.return_value = None

					handle_bin_webhook(hubspot_bin_id="bin-456")

					mock_handle_machine.assert_not_called()

	def test_logs_warning_and_returns_when_machine_ids_empty(self):
		"""api.get_bin_machine_ids returns empty list -> logs warning and returns"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_machine_webhook"
				) as mock_handle_machine:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.logger"
					) as mock_logger:
						mock_get_machines.return_value = []

						handle_bin_webhook(hubspot_bin_id="bin-456")

						mock_logger.assert_called()
						mock_handle_machine.assert_not_called()

	def test_exception_in_get_bin_machine_ids_logged_and_suppressed(self):
		"""api.get_bin_machine_ids raises -> logged and suppressed"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_machine_webhook"
				) as mock_handle_machine:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.log_error"
					) as mock_log_error:
						mock_get_machines.side_effect = ValueError("fetch failed")

						handle_bin_webhook(hubspot_bin_id="bin-456")

						mock_log_error.assert_called()
						mock_handle_machine.assert_not_called()

	def test_exception_in_handle_machine_webhook_logged_and_suppressed(self):
		"""Exception in handle_machine_webhook call -> logged and suppressed, other machines still processed"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler.handle_machine_webhook"
				) as mock_handle_machine:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.log_error"
					) as mock_log_error:
						mock_get_machines.return_value = [
							("2-230363982", "machine-123"),
							("2-230364924", "machine-456"),
						]
						mock_handle_machine.side_effect = [ValueError("sync failed"), None]

						handle_bin_webhook(hubspot_bin_id="bin-789")

						mock_log_error.assert_called()
						self.assertEqual(mock_handle_machine.call_count, 2)

	def test_requires_keyword_only_args(self):
		"""handle_bin_webhook requires keyword-only args (decorated with @retry_via_reenqueue)"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"):
				# Positional args should raise TypeError
				with self.assertRaises(TypeError):
					handle_bin_webhook("bin-456")
