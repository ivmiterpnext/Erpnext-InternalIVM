"""Tests for ivm.integrations.hubspot.reconciler"""

import datetime
from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from ivm.integrations.hubspot import reconciler, routing
from ivm.integrations.hubspot.constants import (
	BIN_TYPE_ID,
	COMPANY_TYPE_ID,
	CONTACT_TYPE_ID,
	DEAL_TYPE_ID,
	NOTE_TYPE_ID,
	SMARTSTATION_TYPE_ID,
)


class TestReconcileNoCheckpoint(FrappeTestCase):
	"""reconcile() with no checkpoint set"""

	def test_no_checkpoint_skips_search(self):
		"""last_checkpoint is falsy → no search, no route, no save."""
		mock_settings = MagicMock()
		mock_settings.last_checkpoint = None

		with patch("ivm.integrations.hubspot.reconciler.frappe.get_single", return_value=mock_settings):
			with patch("ivm.integrations.hubspot.reconciler.api.search_objects") as mock_search:
				with patch("ivm.integrations.hubspot.reconciler.routing.route") as mock_route:
					reconciler.reconcile()

					mock_search.assert_not_called()
					mock_route.assert_not_called()
					mock_settings.save.assert_not_called()


class TestReconcileSinglePage(FrappeTestCase):
	"""reconcile() with a single page of results per object type"""

	def test_single_page_run(self):
		"""Normal run: checkpoint set, single page per type, all results routed."""
		checkpoint_dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
		run_started_at = datetime.datetime(2026, 1, 15, 12, 5, 0)

		mock_settings = MagicMock()
		mock_settings.last_checkpoint = checkpoint_dt

		# Mock search_objects to return 2 results per type, no paging
		def mock_search_fn(object_type, filters, after=None, limit=100):
			return {
				"results": [{"id": "1"}, {"id": "2"}],
				"paging": {},
			}

		with patch("ivm.integrations.hubspot.reconciler.frappe.get_single", return_value=mock_settings):
			with patch("ivm.integrations.hubspot.reconciler.now_datetime", return_value=run_started_at):
				with patch(
					"ivm.integrations.hubspot.reconciler.api.search_objects", side_effect=mock_search_fn
				) as mock_search:
					with patch(
						"ivm.integrations.hubspot.reconciler.routing.route", return_value="enqueued"
					) as mock_route:
						reconciler.reconcile()

						# Verify search_objects called once per object type in SYNC_TARGETS
						self.assertEqual(mock_search.call_count, len(routing.SYNC_TARGETS))

						# Verify route called twice per object type (2 results each)
						self.assertEqual(mock_route.call_count, len(routing.SYNC_TARGETS) * 2)

						# Verify checkpoint advanced by 5 minutes back from run_started_at
						expected_checkpoint = add_to_date(run_started_at, minutes=-5)
						self.assertEqual(mock_settings.last_checkpoint, expected_checkpoint)

						# Verify status set to Success
						self.assertEqual(mock_settings.last_run_status, "Success")
						self.assertEqual(mock_settings.last_run_at, run_started_at)

						# Verify save called
						mock_settings.save.assert_called_once_with(ignore_permissions=True)


class TestReconcilePagination(FrappeTestCase):
	"""reconcile() with multi-page results"""

	def test_pagination_follows_after_cursor(self):
		"""One object type returns 2 pages → search called twice for that type."""
		checkpoint_dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
		run_started_at = datetime.datetime(2026, 1, 15, 12, 5, 0)

		mock_settings = MagicMock()
		mock_settings.last_checkpoint = checkpoint_dt

		# Mock search_objects with side_effect: first call returns paging.next.after,
		# second call returns no paging
		search_responses = [
			{
				"results": [{"id": "1"}],
				"paging": {"next": {"after": "cursor_10"}},
			},
			{
				"results": [{"id": "2"}],
				"paging": {},
			},
		]
		search_call_count = [0]

		def mock_search_fn(object_type, filters, after=None, limit=100):
			# Return different responses for DEAL_TYPE_ID only; others return single page
			if object_type == "deals":
				resp = search_responses[search_call_count[0]]
				search_call_count[0] += 1
				return resp
			return {"results": [{"id": "1"}], "paging": {}}

		with patch("ivm.integrations.hubspot.reconciler.frappe.get_single", return_value=mock_settings):
			with patch("ivm.integrations.hubspot.reconciler.now_datetime", return_value=run_started_at):
				with patch(
					"ivm.integrations.hubspot.reconciler.api.search_objects", side_effect=mock_search_fn
				) as mock_search:
					with patch("ivm.integrations.hubspot.reconciler.routing.route", return_value="enqueued"):
						with patch("ivm.integrations.hubspot.reconciler.time.sleep"):
							reconciler.reconcile()

							# Count calls for "deals" path
							deals_calls = [c for c in mock_search.call_args_list if c[0][0] == "deals"]
							self.assertEqual(len(deals_calls), 2)

							# Verify second call has after="cursor_10"
							self.assertEqual(deals_calls[1][1].get("after"), "cursor_10")


class TestReconcilePageCapHit(FrappeTestCase):
	"""reconcile() when page cap is hit"""

	def test_page_cap_stops_iteration(self):
		"""Hit _MAX_PAGES_PER_TYPE limit → loop exits, warning logged."""
		checkpoint_dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
		run_started_at = datetime.datetime(2026, 1, 15, 12, 5, 0)

		mock_settings = MagicMock()
		mock_settings.last_checkpoint = checkpoint_dt

		# Always return paging.next.after (never empty)
		def mock_search_fn(object_type, filters, after=None, limit=100):
			return {
				"results": [{"id": "1"}],
				"paging": {"next": {"after": "cursor_next"}},
			}

		with patch("ivm.integrations.hubspot.reconciler.frappe.get_single", return_value=mock_settings):
			with patch("ivm.integrations.hubspot.reconciler.now_datetime", return_value=run_started_at):
				with patch(
					"ivm.integrations.hubspot.reconciler.api.search_objects", side_effect=mock_search_fn
				) as mock_search:
					with patch("ivm.integrations.hubspot.reconciler.routing.route", return_value="enqueued"):
						with patch("ivm.integrations.hubspot.reconciler.time.sleep"):
							with patch("ivm.integrations.hubspot.reconciler._MAX_PAGES_PER_TYPE", 2):
								reconciler.reconcile()

								# Count calls for one object type (e.g., deals)
								deals_calls = [c for c in mock_search.call_args_list if c[0][0] == "deals"]
								# Should be exactly 2 (the cap), not 3+
								self.assertEqual(len(deals_calls), 2)

								# Verify no exception raised
								mock_settings.save.assert_called_once()


class TestReconcilePerObjectTypeErrorIsolation(FrappeTestCase):
	"""reconcile() with one object type failing"""

	def test_one_type_fails_others_continue(self):
		"""One object type raises → logged, others still scanned, checkpoint still advances."""
		checkpoint_dt = datetime.datetime(2026, 1, 15, 12, 0, 0)
		run_started_at = datetime.datetime(2026, 1, 15, 12, 5, 0)

		mock_settings = MagicMock()
		mock_settings.last_checkpoint = checkpoint_dt

		def mock_search_fn(object_type, filters, after=None, limit=100):
			# Raise for deals, return empty for others
			if object_type == "deals":
				raise ValueError("HubSpot API error")
			return {"results": [], "paging": {}}

		with patch("ivm.integrations.hubspot.reconciler.frappe.get_single", return_value=mock_settings):
			with patch("ivm.integrations.hubspot.reconciler.now_datetime", return_value=run_started_at):
				with patch(
					"ivm.integrations.hubspot.reconciler.api.search_objects", side_effect=mock_search_fn
				):
					with patch("ivm.integrations.hubspot.reconciler.routing.route", return_value="enqueued"):
						with patch("ivm.integrations.hubspot.reconciler.frappe.log_error") as mock_log_error:
							reconciler.reconcile()

							# Verify log_error called for the failed type
							mock_log_error.assert_called()

							# Verify checkpoint still advanced
							self.assertIsNotNone(mock_settings.last_checkpoint)

							# Verify status is Failed
							self.assertEqual(mock_settings.last_run_status, "Failed")

							# Verify last_run_error mentions the failed type
							self.assertIn(DEAL_TYPE_ID, mock_settings.last_run_error)

							# Verify save still called
							mock_settings.save.assert_called_once()


class TestReconcileInvalidCheckpoint(FrappeTestCase):
	"""reconcile() with invalid checkpoint value"""

	def test_invalid_checkpoint_logs_error_and_returns(self):
		"""get_datetime raises on checkpoint → log_error, no search, return early."""
		mock_settings = MagicMock()
		mock_settings.last_checkpoint = MagicMock()  # Not a valid datetime

		with patch("ivm.integrations.hubspot.reconciler.frappe.get_single", return_value=mock_settings):
			with patch(
				"ivm.integrations.hubspot.reconciler.get_datetime", side_effect=ValueError("Invalid date")
			):
				with patch("ivm.integrations.hubspot.reconciler.api.search_objects") as mock_search:
					with patch("ivm.integrations.hubspot.reconciler.frappe.log_error") as mock_log_error:
						reconciler.reconcile()

						# Verify log_error called
						mock_log_error.assert_called()

						# Verify search never called
						mock_search.assert_not_called()


class TestLastModifiedProperty(FrappeTestCase):
	"""_last_modified_property() returns correct property name"""

	def test_contact_uses_lastmodifieddate(self):
		"""Contact type → lastmodifieddate"""
		self.assertEqual(reconciler._last_modified_property(CONTACT_TYPE_ID), "lastmodifieddate")

	def test_deal_uses_hs_lastmodifieddate(self):
		"""Deal type → hs_lastmodifieddate"""
		self.assertEqual(reconciler._last_modified_property(DEAL_TYPE_ID), "hs_lastmodifieddate")

	def test_company_uses_hs_lastmodifieddate(self):
		"""Company type → hs_lastmodifieddate"""
		self.assertEqual(reconciler._last_modified_property(COMPANY_TYPE_ID), "hs_lastmodifieddate")

	def test_bin_uses_hs_lastmodifieddate(self):
		"""Bin (custom object) → hs_lastmodifieddate"""
		self.assertEqual(reconciler._last_modified_property(BIN_TYPE_ID), "hs_lastmodifieddate")

	def test_note_uses_hs_lastmodifieddate(self):
		"""Note (engagement) → hs_lastmodifieddate"""
		self.assertEqual(reconciler._last_modified_property(NOTE_TYPE_ID), "hs_lastmodifieddate")


class TestSearchPath(FrappeTestCase):
	"""_search_path() resolves object type to API path segment"""

	def test_deal_type_to_deals_path(self):
		"""Deal type ID → deals"""
		self.assertEqual(reconciler._search_path(DEAL_TYPE_ID), "deals")

	def test_contact_type_to_contacts_path(self):
		"""Contact type ID → contacts"""
		self.assertEqual(reconciler._search_path(CONTACT_TYPE_ID), "contacts")

	def test_company_type_to_companies_path(self):
		"""Company type ID → companies"""
		self.assertEqual(reconciler._search_path(COMPANY_TYPE_ID), "companies")

	def test_note_type_to_notes_path(self):
		"""Note type ID → notes (via ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID)"""
		self.assertEqual(reconciler._search_path(NOTE_TYPE_ID), "notes")

	def test_custom_object_type_returns_unchanged(self):
		"""Custom object type ID → returns unchanged"""
		self.assertEqual(reconciler._search_path(SMARTSTATION_TYPE_ID), SMARTSTATION_TYPE_ID)


class TestToEpochMs(FrappeTestCase):
	"""_to_epoch_ms() converts Frappe Datetime to UTC epoch-milliseconds"""

	def test_epoch_ms_with_utc_timezone(self):
		"""Naive datetime in UTC → correct epoch-ms."""
		naive_dt = datetime.datetime(2026, 1, 15, 17, 0, 0)

		with patch("ivm.integrations.hubspot.reconciler.get_system_timezone", return_value="UTC"):
			result = reconciler._to_epoch_ms(naive_dt)

			# 2026-01-15T17:00:00Z in epoch-ms
			expected = int(datetime.datetime(2026, 1, 15, 17, 0, 0, tzinfo=datetime.UTC).timestamp() * 1000)
			self.assertEqual(result, expected)

	def test_epoch_ms_with_eastern_timezone(self):
		"""Naive datetime in America/New_York (EST, UTC-5) → correct epoch-ms."""
		naive_dt = datetime.datetime(2026, 1, 15, 12, 0, 0)  # noon EST

		with patch(
			"ivm.integrations.hubspot.reconciler.get_system_timezone", return_value="America/New_York"
		):
			result = reconciler._to_epoch_ms(naive_dt)

			# Noon EST = 17:00 UTC (EST is UTC-5 in January, no DST)
			expected = int(datetime.datetime(2026, 1, 15, 17, 0, 0, tzinfo=datetime.UTC).timestamp() * 1000)
			self.assertEqual(result, expected)
