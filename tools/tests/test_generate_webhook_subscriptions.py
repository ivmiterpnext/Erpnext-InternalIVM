"""Tests for the webhook subscription generator."""

import json
import tempfile
import unittest
from pathlib import Path

from ivm.integrations.hubspot.routing import SYNC_TARGETS
from tools.generate_webhook_subscriptions import generate_subscriptions


class TestGenerateWebhookSubscriptions(unittest.TestCase):
	"""Test webhook subscription generator."""

	def test_all_sync_targets_have_creation_entry(self) -> None:
		"""Every key in SYNC_TARGETS must have a corresponding object.creation entry."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		creation_entries = {
			entry["objectType"] for entry in subscriptions if entry["subscriptionType"] == "object.creation"
		}

		# Map type IDs to object type names (same logic as generator)
		from ivm.integrations.hubspot.constants import (
			BIN_ASSOCIATION_KEY,
			BIN_TYPE_ID,
			CALL_TYPE_ID,
			COMPANY_TYPE_ID,
			CONTACT_TYPE_ID,
			DEAL_TYPE_ID,
			DEPLOYMENT_SITE_ASSOCIATION_KEY,
			DEPLOYMENT_SITE_TYPE_ID,
			EMAIL_TYPE_ID,
			MACHINE_TYPE_TO_ASSOCIATION_KEY,
			MEETING_TYPE_ID,
			NOTE_TYPE_ID,
			SMARTCENTER_TYPE_ID,
			SMARTLOCKER_TYPE_ID,
			SMARTSTATION_TYPE_ID,
			SMARTSYNC_TYPE_ID,
			SMARTVAULT_TYPE_ID,
			TASK_TYPE_ID,
		)

		expected_names = {
			"DEAL",
			"CONTACT",
			"COMPANY",
			"NOTE",
			"CALL",
			"EMAIL",
			"TASK",
			"MEETING_EVENT",
			DEPLOYMENT_SITE_ASSOCIATION_KEY,
			BIN_ASSOCIATION_KEY,
		}
		expected_names.update(MACHINE_TYPE_TO_ASSOCIATION_KEY.values())

		self.assertEqual(creation_entries, expected_names)

	def test_exactly_one_association_change_entry_for_deal(self) -> None:
		"""Exactly one object.associationChange entry must exist, for DEAL."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		assoc_entries = [
			entry for entry in subscriptions if entry["subscriptionType"] == "object.associationChange"
		]

		self.assertEqual(len(assoc_entries), 1)
		self.assertEqual(assoc_entries[0]["objectType"], "DEAL")

	def test_no_deletion_entries(self) -> None:
		"""No object.deletion entries should exist."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		deletion_entries = [
			entry for entry in subscriptions if entry["subscriptionType"] == "object.deletion"
		]

		self.assertEqual(len(deletion_entries), 0)

	def test_active_false_produces_all_false(self) -> None:
		"""All entries must have active=False when --active=false."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		for entry in subscriptions:
			self.assertFalse(entry["active"])

	def test_active_true_produces_all_true(self) -> None:
		"""All entries must have active=True when --active=true."""
		data = generate_subscriptions(active=True, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		for entry in subscriptions:
			self.assertTrue(entry["active"])

	def test_all_entries_have_required_keys(self) -> None:
		"""Every entry must have subscriptionType, active, and objectType."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		for entry in subscriptions:
			self.assertIn("subscriptionType", entry)
			self.assertIn("active", entry)
			self.assertIn("objectType", entry)

	def test_property_change_entries_have_property_name(self) -> None:
		"""Every object.propertyChange entry must have propertyName."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		for entry in subscriptions:
			if entry["subscriptionType"] == "object.propertyChange":
				self.assertIn("propertyName", entry)

	def test_no_extra_keys_in_entries(self) -> None:
		"""Entries must only have {subscriptionType, active, objectType, propertyName}."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		allowed_keys = {"subscriptionType", "active", "objectType", "propertyName"}

		for entry in subscriptions:
			extra_keys = set(entry.keys()) - allowed_keys
			self.assertEqual(
				extra_keys,
				set(),
				f"Entry has extra keys: {extra_keys}",
			)

	def test_deterministic_output(self) -> None:
		"""Running the generator twice produces byte-identical output."""
		with tempfile.TemporaryDirectory() as tmpdir:
			path1 = Path(tmpdir) / "out1.json"
			path2 = Path(tmpdir) / "out2.json"

			# Generate twice
			data1 = generate_subscriptions(active=False, base_url="https://test.local")
			with open(path1, "w") as f:
				json.dump(data1, f, indent=2)
				f.write("\n")

			data2 = generate_subscriptions(active=False, base_url="https://test.local")
			with open(path2, "w") as f:
				json.dump(data2, f, indent=2)
				f.write("\n")

			# Compare byte-for-byte
			content1 = path1.read_bytes()
			content2 = path2.read_bytes()

			self.assertEqual(content1, content2)

	def test_base_url_in_target_url(self) -> None:
		"""The base URL must appear in the targetUrl."""
		base_url = "https://example.com"
		data = generate_subscriptions(active=False, base_url=base_url)

		target_url = data["config"]["settings"]["targetUrl"]
		self.assertTrue(target_url.startswith(base_url))

	def test_email_excludes_webhook_unsupported_properties(self) -> None:
		"""EMAIL object must exclude hs_email_html and hs_email_subject from propertyChange subscriptions."""
		data = generate_subscriptions(active=False, base_url="https://test.local")
		subscriptions = data["config"]["subscriptions"]["crmObjects"]

		# Collect all propertyChange entries for EMAIL
		email_property_changes = [
			entry
			for entry in subscriptions
			if entry["objectType"] == "EMAIL" and entry["subscriptionType"] == "object.propertyChange"
		]

		# Extract property names
		email_properties = {entry["propertyName"] for entry in email_property_changes}

		# Assert unsupported properties are absent
		self.assertNotIn("hs_email_html", email_properties)
		self.assertNotIn("hs_email_subject", email_properties)

		# Assert EMAIL still has other propertyChange entries (exclusion didn't wipe the object type)
		self.assertGreater(len(email_property_changes), 0)


if __name__ == "__main__":
	unittest.main()
