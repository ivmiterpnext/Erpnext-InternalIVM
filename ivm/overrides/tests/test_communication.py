"""Tests for ivm.overrides.communication.get_emails_patched()."""

import unittest

from ivm.overrides.communication import get_emails_patched

RAW_TRACEBACK_STRING = (
	'"Gajjar, Mayur" <mayur.gajjar@intel.com>, "Support@ivminc.com"\n\t<Support@ivminc.com>, '
	'"Adkins, GeraldX" <geraldx.adkins@intel.com>, "Danielle\n Lanteigne" <d_lanteigne@ivminc.com>'
)


class TestGetEmailsPatched(unittest.TestCase):
	"""Test cases for get_emails_patched()."""

	def test_clean_multi_address_string_returns_all(self):
		"""Clean multi-address string with display names returns all addresses."""
		result = get_emails_patched(
			['"Gajjar, Mayur" <mayur.gajjar@intel.com>, "Adkins, GeraldX" <geraldx.adkins@intel.com>']
		)
		self.assertEqual(result, ["mayur.gajjar@intel.com", "geraldx.adkins@intel.com"])

	def test_recovers_valid_address_from_raw_unfolded_traceback_string(self):
		"""Raw, un-unfolded failing string still yields d_lanteigne@ivminc.com (Layer 2 independent of Layer 1)."""
		result = get_emails_patched([RAW_TRACEBACK_STRING])
		self.assertIn("d_lanteigne@ivminc.com", result)

	def test_empty_and_none_strings_skipped(self):
		"""Empty and None entries are skipped without crashing."""
		result = get_emails_patched(["", None, "valid@example.com"])
		self.assertEqual(result, ["valid@example.com"])

	def test_string_with_no_valid_address_returns_empty_list(self):
		"""String with no valid address returns an empty list without raising."""
		result = get_emails_patched(["Danielle"])
		self.assertEqual(result, [])
