"""Integration tests for ivm.client_portal.utils.signers"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.utils.signers import get_signer_row_for_user

# Real Users created by ERPNextTestSuite's bootstrap — safe to reuse as
# distinct non-Administrator signer identities.
TEST_USER_1 = "test@example.com"
TEST_USER_2 = "test1@example.com"


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
    return doc


class TestGetSignerRowForUser(ERPNextTestSuite):
    """get_signer_row_for_user"""

    def test_returns_none_when_user_has_no_linked_contact(self):
        top_contact = _make_contact("Top Contact Signers Orphan")
        quote = _make_quote(top_contact.name)
        self.assertIsNone(get_signer_row_for_user(quote, user="no-such-user@example.com"))

    def test_returns_none_when_contact_exists_but_not_a_signer(self):
        top_contact = _make_contact("Top Contact Signers NotSigner")
        signer_contact = _make_contact("Signer Contact NotSigner", user=TEST_USER_1)
        _make_contact("Bystander Contact NotSigner", user=TEST_USER_2)
        quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
        self.assertIsNone(get_signer_row_for_user(quote, user=TEST_USER_2))

    def test_returns_matching_row_for_explicit_user(self):
        top_contact = _make_contact("Top Contact Signers Match")
        signer_contact = _make_contact("Signer Contact Match", user=TEST_USER_1)
        quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
        row = get_signer_row_for_user(quote, user=TEST_USER_1)
        self.assertIsNotNone(row)
        self.assertEqual(row.contact, signer_contact.name)

    def test_defaults_to_session_user_when_user_param_omitted(self):
        # ERPNextTestSuite runs as Administrator by default.
        top_contact = _make_contact("Top Contact Signers Default")
        signer_contact = _make_contact("Signer Contact Default", user="Administrator")
        quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
        row = get_signer_row_for_user(quote)
        self.assertIsNotNone(row)
        self.assertEqual(row.contact, signer_contact.name)

    def test_returns_correct_row_among_multiple_signers(self):
        top_contact = _make_contact("Top Contact Signers Multi")
        signer_1 = _make_contact("Signer One Multi", user=TEST_USER_1)
        signer_2 = _make_contact("Signer Two Multi", user=TEST_USER_2)
        quote = _make_quote(
            top_contact.name,
            signers=[{"contact": signer_1.name}, {"contact": signer_2.name}],
        )
        row = get_signer_row_for_user(quote, user=TEST_USER_2)
        self.assertIsNotNone(row)
        self.assertEqual(row.contact, signer_2.name)
