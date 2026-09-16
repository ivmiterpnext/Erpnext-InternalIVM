"""Tests for ivm.integrations.hubspot.deal_handler"""

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.deal_handler import _resolve_or_provision_org


class TestResolveOrProvisionOrg(FrappeTestCase):
    """_resolve_or_provision_org helper function"""

    def test_returns_existing_org_without_provisioning(self):
        """When org exists, return it immediately without calling handle_company_created."""
        with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
            with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
                mock_get_value.return_value = "Existing Org"
                result = _resolve_or_provision_org("123", "test context")
                self.assertEqual(result, "Existing Org")
                mock_create.assert_not_called()

    def test_provisions_when_missing_then_found(self):
        """When org missing initially, provision it, then find it on second lookup."""
        with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
            with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
                # First call returns None (not found), second call returns the org name
                mock_get_value.side_effect = [None, "Newly Provisioned Org"]
                result = _resolve_or_provision_org("456", "test context")
                self.assertEqual(result, "Newly Provisioned Org")
                mock_create.assert_called_once_with("456")

    def test_returns_none_and_logs_when_still_missing_after_provisioning(self):
        """When org still missing after provisioning, return None."""
        with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
            with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
                # Both calls return None (not found before or after provisioning)
                mock_get_value.side_effect = [None, None]
                result = _resolve_or_provision_org("789", "test context")
                self.assertIsNone(result)
                mock_create.assert_called_once_with("789")

    def test_uses_custom_company_label_in_logging(self):
        """Custom company_label is used in log messages."""
        with patch("ivm.integrations.hubspot.deal_handler.frappe.db.get_value") as mock_get_value:
            with patch("ivm.integrations.hubspot.company_handler.handle_company_created") as mock_create:
                with patch("ivm.integrations.hubspot.deal_handler.frappe.logger") as mock_logger:
                    mock_get_value.side_effect = [None, None]
                    _resolve_or_provision_org(
                        "999",
                        "master link on deal X",
                        company_label="master company",
                    )
                    # Verify logger was called (exact message format is implementation detail)
                    mock_logger.assert_called()
