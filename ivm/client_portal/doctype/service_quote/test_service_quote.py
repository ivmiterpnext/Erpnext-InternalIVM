"""Integration tests for ivm.client_portal.doctype.service_quote.service_quote"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.doctype.service_quote.service_quote import has_website_permission

TEST_USER_1 = "test@example.com"


def _make_contact(first_name, user=None):
    contact = frappe.get_doc({
        "doctype": "Contact",
        "first_name": first_name,
        "user": user,
    })
    contact.insert(ignore_permissions=True)
    return contact


def _make_quote(top_contact_name, signers=None):
    doc = frappe.get_doc({
        "doctype": "Service Quote",
        "contact": top_contact_name,
        "sales_representative": "Administrator",
        "customer": "_Test Customer",
        "signers": signers or [],
    })
    doc.insert(ignore_permissions=True)
    with patch("ivm.client_portal.event_handlers.service_quote.on_submit"):
        doc.submit()
    frappe.db.set_value("Service Quote", doc.name, "status", "Sent")
    doc.reload()
    return doc


class TestHasWebsitePermission(ERPNextTestSuite):
    """has_website_permission"""

    def test_guest_is_denied(self):
        top_contact = _make_contact("Top Contact HWP Guest")
        quote = _make_quote(top_contact.name)
        self.assertFalse(has_website_permission(quote, "read", "Guest"))

    def test_denied_when_user_has_no_linked_contact(self):
        top_contact = _make_contact("Top Contact HWP Orphan")
        quote = _make_quote(top_contact.name)
        self.assertFalse(has_website_permission(quote, "read", "no-such-user@example.com"))

    def test_denied_when_contact_not_a_signer(self):
        top_contact = _make_contact("Top Contact HWP NotSigner")
        signer_contact = _make_contact("Signer Contact HWP NotSigner", user="Administrator")
        quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
        self.assertFalse(has_website_permission(quote, "read", TEST_USER_1))

    def test_allowed_when_contact_is_signer(self):
        top_contact = _make_contact("Top Contact HWP Allowed")
        signer_contact = _make_contact("Signer Contact HWP Allowed", user="Administrator")
        quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
        self.assertTrue(has_website_permission(quote, "read", "Administrator"))
