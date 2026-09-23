"""Tests for ivm.overrides.realtime_permission.has_permission()."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivm.overrides.realtime_permission import has_permission


class TestRealtimePermission(unittest.TestCase):
	"""Test cases for has_permission() function."""

	def test_local_doc_name_returns_false_without_calling_frappe_has_permission(self):
		"""Local doc name matching pattern returns False; frappe.has_permission never called."""
		local_name = "new-issue-ab12cd34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			result = has_permission("Issue", local_name)

		self.assertFalse(result)
		mock_has_perm.assert_not_called()

	def test_real_doc_name_calls_frappe_has_permission_and_returns_true(self):
		"""Real doc name (not matching pattern) calls frappe.has_permission; returns True."""
		real_name = "ISS-00001"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", real_name)

		self.assertTrue(result)
		mock_has_perm.assert_called_once_with("Issue", doc=real_name, throw=True)

	def test_permission_denied_raises_frappe_permission_error(self):
		"""Permission denied (frappe.has_permission raises) propagates exception."""
		real_name = "ISS-00002"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.side_effect = frappe.PermissionError("No permission")

			with self.assertRaises(frappe.PermissionError):
				has_permission("Issue", real_name)

	def test_nine_char_suffix_does_not_match_pattern(self):
		"""9-char suffix doesn't match {10} quantifier; frappe.has_permission called."""
		name_9_char = "new-issue-ab12cd34e"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", name_9_char)

		self.assertTrue(result)
		mock_has_perm.assert_called_once()

	def test_eleven_char_suffix_does_not_match_pattern(self):
		"""11-char suffix doesn't match {10} quantifier; frappe.has_permission called."""
		name_11_char = "new-issue-ab12cd34efg"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", name_11_char)

		self.assertTrue(result)
		mock_has_perm.assert_called_once()

	def test_exactly_ten_char_suffix_matches_pattern(self):
		"""Exactly 10-char suffix matches pattern; frappe.has_permission NOT called."""
		name_10_char = "new-issue-ab12cd34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			result = has_permission("Issue", name_10_char)

		self.assertFalse(result)
		mock_has_perm.assert_not_called()

	def test_pattern_requires_new_prefix(self):
		"""Name without 'new-' prefix doesn't match; frappe.has_permission called."""
		name_no_new = "issue-ab12cd34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", name_no_new)

		self.assertTrue(result)
		mock_has_perm.assert_called_once()

	def test_pattern_requires_lowercase_alphanumeric_middle(self):
		"""Name with uppercase in middle section doesn't match; frappe.has_permission called."""
		name_uppercase = "new-Issue-ab12cd34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", name_uppercase)

		self.assertTrue(result)
		mock_has_perm.assert_called_once()

	def test_pattern_requires_lowercase_alphanumeric_suffix(self):
		"""Name with uppercase in suffix doesn't match; frappe.has_permission called."""
		name_uppercase_suffix = "new-issue-ab12CD34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", name_uppercase_suffix)

		self.assertTrue(result)
		mock_has_perm.assert_called_once()

	def test_pattern_allows_hyphens_in_middle_section(self):
		"""Name with hyphens in middle section matches pattern; frappe.has_permission NOT called."""
		name_with_hyphens = "new-my-issue-ab12cd34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			result = has_permission("Issue", name_with_hyphens)

		self.assertFalse(result)
		mock_has_perm.assert_not_called()

	def test_pattern_disallows_hyphens_in_suffix(self):
		"""Name with hyphens in suffix doesn't match; frappe.has_permission called."""
		name_hyphen_suffix = "new-issue-ab12-d34ef"

		with patch("frappe.has_permission") as mock_has_perm:
			mock_has_perm.return_value = True
			result = has_permission("Issue", name_hyphen_suffix)

		self.assertTrue(result)
		mock_has_perm.assert_called_once()
