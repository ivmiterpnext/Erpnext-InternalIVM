"""Integration tests for ivm.deployments.event_handlers.deal"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

_PROVISION = "ivm.deployments.services.provision_client_from_deal.provision_customer_and_icorp_client"
_LINK = "ivm.deployments.services.provision_client_from_deal.link_existing_customer_to_deal"
_MASTER = "ivm.deployments.services.provision_client_from_deal.resolve_and_link_master_client"
_PROJECTS = "ivm.deployments.event_handlers.deal.create_projects_from_deal"


def _ensure_deal_status(status):
    if not frappe.db.exists("CRM Deal Status", status):
        frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
            ignore_permissions=True,
        )


def _make_deal(deal_type=None, customer=None):
    uid = frappe.generate_hash(length=8)
    _ensure_deal_status("Qualification")
    return frappe.get_doc({
        "doctype": "CRM Deal",
        "status": "Qualification",
        "custom_deal_type": deal_type,
        "custom_customer": customer,
        "custom_hubspot_deal_name": f"Test Deal {uid}",
    }).insert(ignore_permissions=True)


def _make_location(crm_deal):
    uid = frappe.generate_hash(length=8)
    return frappe.get_doc({
        "doctype": "Deployment Location",
        "location_name": f"Loc {uid}",
        "crm_deal": crm_deal,
    }).insert(ignore_permissions=True)


@contextmanager
def _mock_deal_services(projects_rv=None):
    """Patch the four service functions called by deal.on_update.

    All are function-local imports in the handler, so patching at the
    source module works (the import resolves the mock at call time).
    """
    projects_rv = projects_rv if projects_rv is not None else []
    with (
        patch(_PROVISION, return_value=None) as mock_prov,
        patch(_LINK, return_value=None) as mock_link,
        patch(_MASTER, return_value=None) as mock_master,
        patch(_PROJECTS, return_value=projects_rv) as mock_proj,
    ):
        yield {
            "provision": mock_prov,
            "link": mock_link,
            "master": mock_master,
            "projects": mock_proj,
        }


class TestDealOnUpdate(ERPNextTestSuite):
    """on_update event handler for CRM Deal"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Company", "IVM"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "IVM",
                "abbr": "IVM",
                "default_currency": "USD",
                "country": "United States",
            }).insert(ignore_permissions=True)

    def test_noop_when_status_not_won(self):
        deal = _make_deal(deal_type="New Business")
        _make_location(deal.name)

        with _mock_deal_services() as mocks:
            deal.custom_hubspot_deal_name = "Updated"
            deal.save(ignore_permissions=True)

            mocks["provision"].assert_not_called()
            mocks["link"].assert_not_called()
            mocks["master"].assert_not_called()
            mocks["projects"].assert_not_called()

    def test_noop_when_status_unchanged(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="New Business")
        _make_location(deal.name)

        frappe.db.set_value("CRM Deal", deal.name, "status", "Won")
        deal.reload()

        with _mock_deal_services() as mocks:
            deal.custom_hubspot_deal_name = "Re-saved"
            deal.save(ignore_permissions=True)

            mocks["provision"].assert_not_called()
            mocks["projects"].assert_not_called()

    def test_throws_when_no_deployment_location(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="New Business")

        with _mock_deal_services():
            deal.status = "Won"
            with self.assertRaises(frappe.ValidationError):
                deal.save(ignore_permissions=True)

    def test_new_business_calls_provision_customer(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="New Business")
        _make_location(deal.name)

        with _mock_deal_services() as mocks:
            deal.status = "Won"
            deal.save(ignore_permissions=True)

            mocks["provision"].assert_called_once_with(deal.name)
            mocks["link"].assert_not_called()

    def test_existing_business_calls_link_existing_customer(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="Existing Business")
        _make_location(deal.name)

        with _mock_deal_services() as mocks:
            deal.status = "Won"
            deal.save(ignore_permissions=True)

            mocks["link"].assert_called_once_with(deal.name)
            mocks["provision"].assert_not_called()

    def test_master_client_failure_logged_not_raised(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="New Business")
        _make_location(deal.name)

        with _mock_deal_services() as mocks:
            mocks["master"].side_effect = ValueError("Simulated failure")
            with patch("frappe.log_error") as mock_log:
                deal.status = "Won"
                deal.save(ignore_permissions=True)

            error_titles = [
                c.kwargs.get("title", "") for c in mock_log.call_args_list
            ]
            self.assertTrue(
                any("Master client resolution failed" in t for t in error_titles)
            )
            mocks["projects"].assert_called_once()

    def test_project_creation_failure_logged_not_raised(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="New Business")
        _make_location(deal.name)

        with _mock_deal_services() as mocks:
            mocks["projects"].side_effect = Exception("Simulated failure")
            with patch("frappe.log_error") as mock_log:
                deal.status = "Won"
                deal.save(ignore_permissions=True)

            error_titles = [
                c.kwargs.get("title", "") for c in mock_log.call_args_list
            ]
            self.assertTrue(
                any("Failed to create Deployments" in t for t in error_titles)
            )

    def test_msgprint_on_successful_project_creation(self):
        _ensure_deal_status("Won")
        deal = _make_deal(deal_type="New Business")
        _make_location(deal.name)

        with _mock_deal_services(projects_rv=["PROJ-0001"]) as mocks:
            with patch("frappe.msgprint") as mock_msg:
                deal.status = "Won"
                deal.save(ignore_permissions=True)

            matching = [
                c for c in mock_msg.call_args_list
                if "Created 1 deployment(s)" in str(c)
            ]
            self.assertTrue(matching)
