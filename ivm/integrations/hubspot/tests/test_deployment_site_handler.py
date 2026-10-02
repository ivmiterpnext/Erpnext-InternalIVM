"""Tests for ivm.integrations.hubspot.deployment_site_handler"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import DEPLOYMENT_SITE_TYPE_ID
from ivm.integrations.hubspot.deployment_site_handler import (
	_map_properties,
	_resolve_deal_for_site,
	_sync_site_core,
	_upsert_location_from_webhook,
	sync_bin,
	sync_machine,
	sync_site,
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
					mock_ensure.return_value = "Deal-001"

					result = _resolve_deal_for_site("site-456")

					self.assertEqual(result, "Deal-001")
					mock_ensure.assert_called_once_with("deal-123")

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
		"""Existing Deployment Location found -> loads and updates it, returns False"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value") as mock_get_value:
			with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.get_doc") as mock_get_doc:
				with patch("ivm.integrations.hubspot.deployment_site_handler.save_doc") as mock_save_doc:
					with patch("ivm.integrations.hubspot.deployment_site_handler._apply_site_properties"):
						with patch("ivm.integrations.hubspot.deployment_site_handler._apply_machine_data"):
							mock_get_value.return_value = "Location-001"
							mock_doc = MagicMock()
							mock_doc.doctype = "Deployment Location"
							mock_doc.name = "Location-001"
							mock_doc.location_name = "Existing Site"
							mock_get_doc.return_value = mock_doc

							is_new = _upsert_location_from_webhook(
								"Deal-001",
								"site-456",
								{"site_location_name": "Site Name"},
								{},
							)

							self.assertFalse(is_new)
							mock_get_doc.assert_called_once_with("Deployment Location", "Location-001")
							mock_save_doc.assert_called_once_with(mock_doc, "site")
							mock_doc.insert.assert_not_called()

	def test_creates_new_location_when_not_found(self):
		"""No existing Deployment Location -> creates new one, returns True"""
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

						is_new = _upsert_location_from_webhook(
							"Deal-001",
							"site-456",
							{"site_location_name": "Site Name"},
							{},
						)

						self.assertTrue(is_new)
						mock_new_doc.assert_called_once_with("Deployment Location")
						self.assertEqual(mock_doc.crm_deal, "Deal-001")
						self.assertEqual(mock_doc.hubspot_site_id, "site-456")
						mock_doc.insert.assert_called_once_with(ignore_permissions=True)

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


class TestSyncSite(FrappeTestCase):
	"""sync_site function"""

	def test_resolves_deal_and_syncs(self):
		"""Site resolved to deal -> calls _sync_site_core with trigger_deal_sync=True"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"
			) as mock_resolve:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._sync_site_core"
				) as mock_sync_core:
					mock_resolve.return_value = "Deal-001"

					sync_site(hubspot_site_id="site-456")

					mock_resolve.assert_called_once_with("site-456")
					mock_sync_core.assert_called_once_with("site-456", "Deal-001", trigger_deal_sync=True)

	def test_no_deal_resolved_skips_sync(self):
		"""No deal resolved -> _sync_site_core never called"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"
			) as mock_resolve:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._sync_site_core"
				) as mock_sync_core:
					mock_resolve.return_value = None

					sync_site(hubspot_site_id="site-456")

					mock_sync_core.assert_not_called()

	def test_requires_keyword_only_args(self):
		"""sync_site requires keyword-only args (decorated with @retry_via_reenqueue)"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch("ivm.integrations.hubspot.deployment_site_handler._resolve_deal_for_site"):
				# Positional args should raise TypeError
				with self.assertRaises(TypeError):
					sync_site("site-456")


class TestSyncSiteCore(FrappeTestCase):
	"""_sync_site_core function"""

	def test_upserts_and_logs(self):
		"""Fetches site data, upserts location, logs result"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object") as mock_get_obj:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._fetch_site_machines"
			) as mock_fetch_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._upsert_location_from_webhook"
				) as mock_upsert:
					with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
						mock_get_obj.return_value = {"properties": {"site_location_name": "Site A"}}
						mock_fetch_machines.return_value = {}
						mock_upsert.return_value = False  # Not new

						_sync_site_core("site-456", "Deal-001", trigger_deal_sync=True)

						mock_get_obj.assert_called_once()
						mock_fetch_machines.assert_called_once_with("site-456")
						mock_upsert.assert_called_once()

	def test_new_location_with_trigger_enqueues_deal_sync(self):
		"""New location created + trigger_deal_sync=True -> enqueues deal sync"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object") as mock_get_obj:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._fetch_site_machines"
			) as mock_fetch_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._upsert_location_from_webhook"
				) as mock_upsert:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.frappe.db.get_value"
					) as mock_get_value:
						with patch(
							"ivm.integrations.hubspot.deployment_site_handler.enqueue_sync"
						) as mock_enqueue:
							with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
								mock_get_obj.return_value = {"properties": {}}
								mock_fetch_machines.return_value = {}
								mock_upsert.return_value = True  # Is new
								mock_get_value.return_value = "hs-deal-123"

								_sync_site_core("site-456", "Deal-001", trigger_deal_sync=True)

								mock_enqueue.assert_called_once()
								args = mock_enqueue.call_args[0]
								self.assertTrue(args[0].endswith(".sync_deal"))
								self.assertEqual(args[2], "hs-deal-123")

	def test_new_location_without_trigger_does_not_enqueue(self):
		"""New location created but trigger_deal_sync=False -> no deal sync enqueue"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object") as mock_get_obj:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._fetch_site_machines"
			) as mock_fetch_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._upsert_location_from_webhook"
				) as mock_upsert:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.enqueue_sync"
					) as mock_enqueue:
						with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
							mock_get_obj.return_value = {"properties": {}}
							mock_fetch_machines.return_value = {}
							mock_upsert.return_value = True  # Is new

							_sync_site_core("site-456", "Deal-001", trigger_deal_sync=False)

							mock_enqueue.assert_not_called()

	def test_existing_location_never_enqueues_even_with_trigger_true(self):
		"""Existing location updated + trigger_deal_sync=True -> no deal sync enqueue"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object") as mock_get_obj:
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler._fetch_site_machines"
			) as mock_fetch_machines:
				with patch(
					"ivm.integrations.hubspot.deployment_site_handler._upsert_location_from_webhook"
				) as mock_upsert:
					with patch(
						"ivm.integrations.hubspot.deployment_site_handler.enqueue_sync"
					) as mock_enqueue:
						with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
							mock_get_obj.return_value = {"properties": {}}
							mock_fetch_machines.return_value = {}
							mock_upsert.return_value = False  # Not new

							_sync_site_core("site-456", "Deal-001", trigger_deal_sync=True)

							mock_enqueue.assert_not_called()

	def test_no_blanket_exception_handling(self):
		"""Exceptions propagate (no catch-all) per design rule R2"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.api.get_custom_object") as mock_get_obj:
			mock_get_obj.side_effect = ValueError("API error")

			with self.assertRaises(ValueError):
				_sync_site_core("site-456", "Deal-001", trigger_deal_sync=True)


class TestSyncMachine(FrappeTestCase):
	"""sync_machine function"""

	def test_enqueues_sync_site_for_each_site_id(self):
		"""Machine linked to 2 sites -> enqueues sync_site for each"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch("ivm.integrations.hubspot.deployment_site_handler.enqueue_sync") as mock_enqueue:
					mock_get_sites.return_value = ["site-1", "site-2"]

					sync_machine(machine_type_id="2-230236986", hubspot_machine_id="m-1")

					self.assertEqual(mock_enqueue.call_count, 2)
					calls = mock_enqueue.call_args_list
					# First call
					self.assertTrue(calls[0][0][0].endswith(".sync_site"))
					self.assertEqual(calls[0][1]["hubspot_site_id"], "site-1")
					# Second call
					self.assertTrue(calls[1][0][0].endswith(".sync_site"))
					self.assertEqual(calls[1][1]["hubspot_site_id"], "site-2")

	def test_no_sites_logs_warning_and_returns(self):
		"""Machine linked to no sites -> logs warning, no enqueue"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_machine_site_ids"
			) as mock_get_sites:
				with patch("ivm.integrations.hubspot.deployment_site_handler.enqueue_sync") as mock_enqueue:
					with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
						mock_get_sites.return_value = []

						sync_machine(machine_type_id="2-230236986", hubspot_machine_id="m-1")

						mock_enqueue.assert_not_called()


class TestSyncBin(FrappeTestCase):
	"""sync_bin function"""

	def test_enqueues_sync_machine_for_each_pair(self):
		"""Bin linked to 2 machines -> enqueues sync_machine for each"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch("ivm.integrations.hubspot.deployment_site_handler.enqueue_sync") as mock_enqueue:
					mock_get_machines.return_value = [
						("2-230236986", "m-1"),
						("2-230363982", "m-2"),
					]

					sync_bin(hubspot_bin_id="bin-1")

					self.assertEqual(mock_enqueue.call_count, 2)
					calls = mock_enqueue.call_args_list
					# First call
					self.assertTrue(calls[0][0][0].endswith(".sync_machine"))
					self.assertEqual(calls[0][1]["machine_type_id"], "2-230236986")
					self.assertEqual(calls[0][1]["hubspot_machine_id"], "m-1")
					# Second call
					self.assertTrue(calls[1][0][0].endswith(".sync_machine"))
					self.assertEqual(calls[1][1]["machine_type_id"], "2-230363982")
					self.assertEqual(calls[1][1]["hubspot_machine_id"], "m-2")

	def test_no_machines_logs_warning_and_returns(self):
		"""Bin linked to no machines -> logs warning, no enqueue"""
		with patch("ivm.integrations.hubspot.deployment_site_handler.set_acting_user"):
			with patch(
				"ivm.integrations.hubspot.deployment_site_handler.api.get_bin_machine_ids"
			) as mock_get_machines:
				with patch("ivm.integrations.hubspot.deployment_site_handler.enqueue_sync") as mock_enqueue:
					with patch("ivm.integrations.hubspot.deployment_site_handler.frappe.logger"):
						mock_get_machines.return_value = []

						sync_bin(hubspot_bin_id="bin-1")

						mock_enqueue.assert_not_called()
