"""Tests for ivm.overrides.queue_overload_fix._check_queue_size_patched()."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivm.overrides.queue_overload_fix import _check_queue_size_patched


class TestQueueOverloadFix(unittest.TestCase):
	"""Test cases for _check_queue_size_patched() function."""

	def test_permission_error_does_not_shadow_queue_overloaded(self):
		"""PermissionError from has_permission does not shadow QueueOverloaded exception."""
		q = MagicMock()
		q.count = 600

		with patch("frappe.utils.background_jobs.MAX_QUEUED_JOBS", 500):
			with patch("frappe.utils.background_jobs._site_count", return_value=0):
				with patch("frappe.has_permission", side_effect=PermissionError("No permission")):
					with self.assertRaises(frappe.QueueOverloaded):
						_check_queue_size_patched(q)

	def test_below_threshold_does_not_raise(self):
		"""Queue below threshold does not raise; has_permission never called."""
		q = MagicMock()
		q.count = 400

		with patch("frappe.utils.background_jobs.MAX_QUEUED_JOBS", 500):
			with patch("frappe.utils.background_jobs._site_count", return_value=0):
				with patch("frappe.has_permission") as mock_has_perm:
					_check_queue_size_patched(q)
					mock_has_perm.assert_not_called()

	def test_at_threshold_raises_queue_overloaded(self):
		"""Queue at exact threshold raises QueueOverloaded."""
		q = MagicMock()
		q.count = 500

		with patch("frappe.utils.background_jobs.MAX_QUEUED_JOBS", 500):
			with patch("frappe.utils.background_jobs._site_count", return_value=0):
				with patch("frappe.has_permission", return_value=False):
					with self.assertRaises(frappe.QueueOverloaded):
						_check_queue_size_patched(q)

	def test_permission_granted_includes_primary_action(self):
		"""When has_permission returns True, primary_action is included in throw."""
		q = MagicMock()
		q.count = 600

		with patch("frappe.utils.background_jobs.MAX_QUEUED_JOBS", 500):
			with patch("frappe.utils.background_jobs._site_count", return_value=0):
				with patch("frappe.has_permission", return_value=True):
					with patch("frappe.throw") as mock_throw:
						_check_queue_size_patched(q)
						mock_throw.assert_called_once()
						call_kwargs = mock_throw.call_args[1]
						self.assertIsNotNone(call_kwargs.get("primary_action"))
						self.assertEqual(call_kwargs["primary_action"]["label"], "Monitor System Health")

	def test_permission_denied_excludes_primary_action(self):
		"""When has_permission returns False, primary_action is None."""
		q = MagicMock()
		q.count = 600

		with patch("frappe.utils.background_jobs.MAX_QUEUED_JOBS", 500):
			with patch("frappe.utils.background_jobs._site_count", return_value=0):
				with patch("frappe.has_permission", return_value=False):
					with patch("frappe.throw") as mock_throw:
						_check_queue_size_patched(q)
						mock_throw.assert_called_once()
						call_kwargs = mock_throw.call_args[1]
						self.assertIsNone(call_kwargs.get("primary_action"))

	def test_exception_in_has_permission_excludes_primary_action(self):
		"""When has_permission raises any exception, primary_action is None."""
		q = MagicMock()
		q.count = 600

		with patch("frappe.utils.background_jobs.MAX_QUEUED_JOBS", 500):
			with patch("frappe.utils.background_jobs._site_count", return_value=0):
				with patch("frappe.has_permission", side_effect=RuntimeError("Some error")):
					with patch("frappe.throw") as mock_throw:
						_check_queue_size_patched(q)
						mock_throw.assert_called_once()
						call_kwargs = mock_throw.call_args[1]
						self.assertIsNone(call_kwargs.get("primary_action"))
