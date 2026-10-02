"""Tests for ivm.integrations.hubspot.routing.route()"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot import routing
from ivm.integrations.hubspot.constants import (
	BIN_TYPE_ID,
	COMPANY_TYPE_ID,
	CONTACT_TYPE_ID,
	DEAL_TYPE_ID,
	DEPLOYMENT_SITE_TYPE_ID,
	NOTE_TYPE_ID,
	SMARTSTATION_TYPE_ID,
)


class TestRoute(FrappeTestCase):
	"""routing.route() dispatch logic"""

	def test_unhandled_object_type_returns_unhandled(self):
		"""No sync target registered for the object type -> unhandled, nothing enqueued."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync") as mock_enqueue:
			self.assertEqual(routing.route("9-999999", "123"), "unhandled")
			mock_enqueue.assert_not_called()

	def test_deal_always_enqueues(self):
		"""Deal has no gate -> always enqueued."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued") as mock_enqueue:
			self.assertEqual(routing.route(DEAL_TYPE_ID, "1"), "enqueued")
			mock_enqueue.assert_called_once_with(
				"ivm.integrations.hubspot.deal_handler.sync_deal",
				DEAL_TYPE_ID,
				"1",
				hubspot_deal_id="1",
			)

	def test_contact_gate_drops_unknown_contact(self):
		"""Contact not linked to any deal locally -> dropped, nothing enqueued."""
		with patch("ivm.integrations.hubspot.routing.frappe.db.exists", return_value=None):
			with patch("ivm.integrations.hubspot.routing.enqueue_sync") as mock_enqueue:
				self.assertEqual(routing.route(CONTACT_TYPE_ID, "42"), "dropped")
				mock_enqueue.assert_not_called()

	def test_contact_gate_passes_known_contact(self):
		"""Contact already linked locally -> enqueued."""
		with patch("ivm.integrations.hubspot.routing.frappe.db.exists", return_value="CONTACT-001"):
			with patch(
				"ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued"
			) as mock_enqueue:
				self.assertEqual(routing.route(CONTACT_TYPE_ID, "42"), "enqueued")
				mock_enqueue.assert_called_once_with(
					"ivm.integrations.hubspot.contact_handler.sync_contact",
					CONTACT_TYPE_ID,
					"42",
					hubspot_contact_id="42",
				)

	def test_company_gate_drops_unknown_company(self):
		"""Company not linked to any deal locally -> dropped, nothing enqueued."""
		with patch("ivm.integrations.hubspot.routing.frappe.db.exists", return_value=None):
			with patch("ivm.integrations.hubspot.routing.enqueue_sync") as mock_enqueue:
				self.assertEqual(routing.route(COMPANY_TYPE_ID, "7"), "dropped")
				mock_enqueue.assert_not_called()

	def test_company_gate_passes_known_company(self):
		"""Company already linked locally -> enqueued."""
		with patch("ivm.integrations.hubspot.routing.frappe.db.exists", return_value="ORG-001"):
			with patch(
				"ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued"
			) as mock_enqueue:
				self.assertEqual(routing.route(COMPANY_TYPE_ID, "7"), "enqueued")
				mock_enqueue.assert_called_once()

	def test_site_always_enqueues_no_gate(self):
		"""Custom objects (site/bin/machine) have no local-existence gate."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued"):
			self.assertEqual(routing.route(DEPLOYMENT_SITE_TYPE_ID, "5"), "enqueued")

	def test_bin_always_enqueues_no_gate(self):
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued"):
			self.assertEqual(routing.route(BIN_TYPE_ID, "11"), "enqueued")

	def test_machine_kwargs_include_type_id(self):
		"""A machine type's sync target closes over its own type ID."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued") as mock_enqueue:
			routing.route(SMARTSTATION_TYPE_ID, "9")
			mock_enqueue.assert_called_once_with(
				"ivm.integrations.hubspot.deployment_site_handler.sync_machine",
				SMARTSTATION_TYPE_ID,
				"9",
				machine_type_id=SMARTSTATION_TYPE_ID,
				hubspot_machine_id="9",
			)

	def test_engagement_kwargs_include_engagement_type_id(self):
		"""An engagement type's sync target closes over its own type ID."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="queued") as mock_enqueue:
			routing.route(NOTE_TYPE_ID, "3")
			mock_enqueue.assert_called_once_with(
				"ivm.integrations.hubspot.activity_handler.sync_engagement",
				NOTE_TYPE_ID,
				"3",
				engagement_type_id=NOTE_TYPE_ID,
				engagement_id="3",
			)

	def test_skipped_result_passed_through(self):
		"""enqueue_sync's 'skipped' result is surfaced as-is."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="skipped"):
			self.assertEqual(routing.route(DEAL_TYPE_ID, "1"), "skipped")

	def test_followup_result_collapses_to_enqueued(self):
		"""enqueue_sync's 'followup' result still counts as 'enqueued' to the caller."""
		with patch("ivm.integrations.hubspot.routing.enqueue_sync", return_value="followup"):
			self.assertEqual(routing.route(DEAL_TYPE_ID, "1"), "enqueued")
