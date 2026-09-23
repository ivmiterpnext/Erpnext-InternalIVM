"""Integration tests for ivm.deployments.services.provision_client_from_deal"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.provision_client_from_deal import (
	get_primary_contact,
	link_existing_customer_to_deal,
	provision_customer_and_icorp_client,
	resolve_and_link_master_client,
)

_ICORP_POST = "ivm.deployments.services.provision_client_from_deal.icorp_api_post"
_EXTRACT_ID = "ivm.deployments.services.provision_client_from_deal.extract_id"


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_organization(name_hint="Org", industry=None, website=None):
	doc = frappe.get_doc(
		{
			"doctype": "CRM Organization",
			"organization_name": f"{name_hint} {frappe.generate_hash(length=8)}",
			"industry": industry,
			"website": website,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_contact(first_name, email=None):
	data = {"doctype": "Contact", "first_name": first_name}
	if email:
		data["email_ids"] = [{"email_id": email, "is_primary": 1}]
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)
	return doc


def _make_deal(
	organization=None,
	custom_customer=None,
	custom_master_organization=None,
	custom_master_customer=None,
	contacts=None,
):
	_ensure_deal_status("Qualification")
	return frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"organization": organization,
			"custom_customer": custom_customer,
			"custom_master_organization": custom_master_organization,
			"custom_master_customer": custom_master_customer,
			"contacts": contacts or [],
			"custom_hubspot_deal_name": f"Test Deal {frappe.generate_hash(length=8)}",
		}
	).insert(ignore_permissions=True)


def _make_customer(name_hint="Cust", industry=None, website=None):
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"{name_hint} {frappe.generate_hash(length=8)}",
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
			"industry": industry,
			"website": website,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestGetPrimaryContact(ERPNextTestSuite):
	def test_returns_primary_row(self):
		contact = _make_contact("Primary GPC")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 1}])
		result = get_primary_contact(deal)
		self.assertEqual(result.name, contact.name)

	def test_returns_none_when_no_contacts(self):
		deal = _make_deal(contacts=[])
		self.assertIsNone(get_primary_contact(deal))

	def test_falls_back_to_first_when_none_primary(self):
		contact = _make_contact("Only GPC")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 0}])
		result = get_primary_contact(deal)
		self.assertEqual(result.name, contact.name)


class TestProvisionCustomerAndIcorpClient(ERPNextTestSuite):
	def test_no_organization_returns_none(self):
		deal = _make_deal(organization=None)
		result = provision_customer_and_icorp_client(deal.name)
		self.assertIsNone(result)

	def test_reuses_existing_matching_customer(self):
		# industry/website left blank deliberately -- see test_falls_back_to_organization_match
		org = _make_organization("ReuseOrg")
		existing_customer = _make_customer("ReuseOrg")
		frappe.db.set_value("Customer", existing_customer.name, "customer_name", org.organization_name)

		deal = _make_deal(organization=org.name, contacts=[])
		with patch(_ICORP_POST) as mock_post:
			result = provision_customer_and_icorp_client(deal.name)

		self.assertEqual(result, existing_customer.name)
		mock_post.assert_not_called()

	def test_creates_new_customer_when_no_match(self):
		org = _make_organization("BrandNewOrg")
		contact = _make_contact("Primary PCIC", email="pcic@example.com")
		deal = _make_deal(organization=org.name, contacts=[{"contact": contact.name, "is_primary": 1}])

		with (
			patch(_ICORP_POST, return_value={"contact": {"id": 111}}),
			patch(_EXTRACT_ID, side_effect=[111, 222]),
		):
			result = provision_customer_and_icorp_client(deal.name)

		self.assertTrue(frappe.db.exists("Customer", {"customer_name": org.organization_name}))
		self.assertEqual(
			result, frappe.db.get_value("Customer", {"customer_name": org.organization_name}, "name")
		)
		deal.reload()
		self.assertEqual(deal.custom_customer, result)

	def test_icorp_client_id_stored_on_customer(self):
		org = _make_organization("IcorpIdOrg")
		contact = _make_contact("Primary IcorpId", email="icorpid@example.com")
		deal = _make_deal(organization=org.name, contacts=[{"contact": contact.name, "is_primary": 1}])

		with (
			patch(_ICORP_POST, return_value={"contact": {"id": 111}}),
			patch(_EXTRACT_ID, side_effect=[111, 999]),
		):
			result = provision_customer_and_icorp_client(deal.name)

		self.assertEqual(frappe.db.get_value("Customer", result, "icorp_client_id"), "999")

	def test_no_primary_contact_still_creates_customer(self):
		org = _make_organization("NoContactOrg")
		deal = _make_deal(organization=org.name, contacts=[])

		with patch(_ICORP_POST) as mock_post:
			result = provision_customer_and_icorp_client(deal.name)

		self.assertTrue(result)
		mock_post.assert_not_called()


class TestLinkExistingCustomerToDeal(ERPNextTestSuite):
	def test_uses_custom_customer_when_already_set(self):
		customer = _make_customer("AlreadySet")
		deal = _make_deal(custom_customer=customer.name)
		result = link_existing_customer_to_deal(deal.name)
		self.assertEqual(result, customer.name)

	def test_falls_back_to_organization_match(self):
		# industry/website are Link/plain fields requiring real matching
		# values to compare -- leaving both blank means _find_existing_customer
		# matches on organization_name alone, which is sufficient here.
		org = _make_organization("FallbackOrg")
		customer = _make_customer("FallbackOrg")
		frappe.db.set_value("Customer", customer.name, "customer_name", org.organization_name)
		deal = _make_deal(organization=org.name)

		result = link_existing_customer_to_deal(deal.name)
		self.assertEqual(result, customer.name)
		deal.reload()
		self.assertEqual(deal.custom_customer, customer.name)

	def test_throws_when_no_customer_resolvable(self):
		deal = _make_deal()
		with self.assertRaises(frappe.ValidationError):
			link_existing_customer_to_deal(deal.name)


class TestResolveAndLinkMasterClient(ERPNextTestSuite):
	def test_noop_when_neither_master_field_set(self):
		customer = _make_customer("NoMaster")
		deal = _make_deal(custom_customer=customer.name)
		result = resolve_and_link_master_client(deal.name)
		self.assertIsNone(result)

	def test_noop_when_no_custom_customer_resolved_yet(self):
		deal = _make_deal(custom_master_customer=None)
		frappe.db.set_value("CRM Deal", deal.name, "custom_master_organization", "SOME-ORG")
		result = resolve_and_link_master_client(deal.name)
		self.assertIsNone(result)

	def test_uses_existing_master_customer_field(self):
		customer = _make_customer("HasCustomer")
		master = _make_customer("MasterCust")
		deal = _make_deal(custom_customer=customer.name, custom_master_customer=master.name)

		result = resolve_and_link_master_client(deal.name)
		self.assertEqual(result, master.name)
		self.assertEqual(
			frappe.db.get_value("Customer", customer.name, "custom_master_customer"), master.name
		)

	def test_creates_master_customer_from_master_organization(self):
		customer = _make_customer("HasCustomer2")
		master_org = _make_organization("MasterOrgToCreate")
		deal = _make_deal(custom_customer=customer.name, custom_master_organization=master_org.name)

		result = resolve_and_link_master_client(deal.name)
		self.assertTrue(frappe.db.exists("Customer", {"customer_name": master_org.organization_name}))
		self.assertEqual(
			result, frappe.db.get_value("Customer", {"customer_name": master_org.organization_name}, "name")
		)

	def test_self_referential_link_skipped(self):
		customer = _make_customer("SelfRef")
		deal = _make_deal(custom_customer=customer.name, custom_master_customer=customer.name)
		result = resolve_and_link_master_client(deal.name)
		self.assertIsNone(result)
