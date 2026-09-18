"""Integration tests for ivm.client_portal.services.dashboard"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.dashboard import get_dashboard_summary

TEST_USER = "test@example.com"


def _make_contact_for_user(user, customer=None):
    data = {"doctype": "Contact", "first_name": f"Contact {frappe.generate_hash(length=6)}", "user": user}
    doc = frappe.get_doc(data)
    doc.insert(ignore_permissions=True)
    if customer:
        doc.append("links", {"link_doctype": "Customer", "link_name": customer})
        doc.save(ignore_permissions=True)
    return doc


def _make_customer():
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": frappe.generate_hash(length=10),
        "customer_group": "_Test Customer Group",
        "territory": "_Test Territory",
    })
    doc.insert(ignore_permissions=True)
    return doc


class TestGetDashboardSummary(ERPNextTestSuite):
    def test_no_contact_returns_zeroes(self):
        result = get_dashboard_summary("no-such-user@example.com")
        self.assertEqual(result, {"pending_quote_count": 0, "active_deployment_count": 0})

    def test_pending_quote_count_counts_sent_and_partially_accepted(self):
        contact = _make_contact_for_user(TEST_USER)
        quote = frappe.get_doc({
            "doctype": "Service Quote",
            "contact": contact.name,
            "sales_representative": "Administrator",
            "customer": "_Test Customer",
            "signers": [{"contact": contact.name, "status": "Pending"}],
        })
        quote.insert(ignore_permissions=True)
        from unittest.mock import patch
        with patch("ivm.client_portal.event_handlers.service_quote.on_submit"):
            quote.submit()
        frappe.db.set_value("Service Quote", quote.name, "status", "Sent")

        result = get_dashboard_summary(TEST_USER)
        self.assertEqual(result["pending_quote_count"], 1)

    def test_active_deployment_count_filters_by_customer_and_type(self):
        customer = _make_customer()
        _make_contact_for_user(TEST_USER, customer=customer.name)

        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": f"Active Deploy {frappe.generate_hash(length=6)}",
            "customer": customer.name,
            "company": "_Test Company",
            "project_type": "Deployment",
        })
        project.insert(ignore_permissions=True)

        result = get_dashboard_summary(TEST_USER)
        self.assertEqual(result["active_deployment_count"], 1)

    def test_cancelled_deployments_excluded(self):
        customer = _make_customer()
        _make_contact_for_user(TEST_USER, customer=customer.name)

        project = frappe.get_doc({
            "doctype": "Project",
            "project_name": f"Cancelled Deploy {frappe.generate_hash(length=6)}",
            "customer": customer.name,
            "company": "_Test Company",
            "project_type": "Deployment",
            "status": "Cancelled",
        })
        project.insert(ignore_permissions=True)

        result = get_dashboard_summary(TEST_USER)
        self.assertEqual(result["active_deployment_count"], 0)
