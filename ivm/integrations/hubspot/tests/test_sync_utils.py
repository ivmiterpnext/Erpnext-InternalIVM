"""Tests for ivm.integrations.hubspot.sync_utils"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.sync_utils import ConcurrentCreateConflict, retry_via_reenqueue


class TestRetryViaReenqueue(FrappeTestCase):
    """retry_via_reenqueue decorator"""

    def test_returns_value_on_success(self):
        """Decorator passes through return value on success and never calls enqueue."""
        @retry_via_reenqueue()
        def stub_func(value: int) -> int:
            return value * 2

        with patch("ivm.integrations.hubspot.sync_utils.frappe.enqueue") as mock_enqueue:
            result = stub_func(value=5)
            self.assertEqual(result, 10)
            mock_enqueue.assert_not_called()

    def test_reenqueues_on_concurrent_create_conflict(self):
        """Decorator catches ConcurrentCreateConflict and re-enqueues."""
        @retry_via_reenqueue()
        def stub_func(deal_id: str) -> None:
            raise ConcurrentCreateConflict("CRM Deal", "hubspot_deal_id", deal_id)

        with patch("ivm.integrations.hubspot.sync_utils.frappe.enqueue") as mock_enqueue:
            result = stub_func(deal_id="123")
            self.assertIsNone(result)
            mock_enqueue.assert_called_once()
            call_args = mock_enqueue.call_args
            self.assertEqual(call_args[0][0], f"{stub_func.__module__}.stub_func")
            self.assertEqual(call_args[1]["queue"], "long")
            self.assertEqual(call_args[1]["deal_id"], "123")

    def test_reenqueues_on_rate_limit_exhausted(self):
        """Decorator catches HubSpotRateLimitExhausted and re-enqueues."""
        @retry_via_reenqueue()
        def stub_func(company_id: str) -> None:
            raise api.HubSpotRateLimitExhausted(retry_after_seconds=30.0)

        with patch("ivm.integrations.hubspot.sync_utils.frappe.enqueue") as mock_enqueue:
            result = stub_func(company_id="456")
            self.assertIsNone(result)
            mock_enqueue.assert_called_once()
            call_args = mock_enqueue.call_args
            self.assertEqual(call_args[0][0], f"{stub_func.__module__}.stub_func")
            self.assertEqual(call_args[1]["queue"], "long")
            self.assertEqual(call_args[1]["company_id"], "456")

    def test_does_not_catch_unrelated_exception(self):
        """Decorator does not catch exceptions outside the default tuple."""
        @retry_via_reenqueue()
        def stub_func() -> None:
            raise ValueError("Something went wrong")

        with patch("ivm.integrations.hubspot.sync_utils.frappe.enqueue") as mock_enqueue:
            with self.assertRaises(ValueError):
                stub_func()
            mock_enqueue.assert_not_called()

    def test_respects_custom_exception_tuple(self):
        """Decorator respects custom exceptions parameter."""
        @retry_via_reenqueue(exceptions=(ValueError,))
        def stub_func_custom() -> None:
            raise ValueError("Custom exception")

        with patch("ivm.integrations.hubspot.sync_utils.frappe.enqueue") as mock_enqueue:
            result = stub_func_custom()
            self.assertIsNone(result)
            mock_enqueue.assert_called_once()

    def test_custom_exceptions_excludes_default(self):
        """When custom exceptions are specified, defaults are excluded."""
        @retry_via_reenqueue(exceptions=(ValueError,))
        def stub_func_exclude() -> None:
            raise api.HubSpotRateLimitExhausted(retry_after_seconds=30.0)

        with patch("ivm.integrations.hubspot.sync_utils.frappe.enqueue") as mock_enqueue:
            with self.assertRaises(api.HubSpotRateLimitExhausted):
                stub_func_exclude()
            mock_enqueue.assert_not_called()
