"""Integration tests for ivm.deployments.services.provision_client_from_deal (contact helpers)"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.provision_client_from_deal import (
	_link_contact_to_customer,
	get_primary_contact,
)


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_contact(first_name, email=None):
	data = {"doctype": "Contact", "first_name": first_name}
	if email:
		data["email_ids"] = [{"email_id": email, "is_primary": 1}]
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)
	return doc


def _make_deal(contacts=None):
	_ensure_deal_status("Qualification")
	return frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"contacts": contacts or [],
			"custom_hubspot_deal_name": f"Test Deal {frappe.generate_hash(length=8)}",
		}
	).insert(ignore_permissions=True)


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


def _make_customer(customer_name):
	customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	return frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": "Company",
			"customer_group": customer_group,
			"territory": "All Territories",
		}
	).insert(ignore_permissions=True)


class TestLinkContactToCustomer(ERPNextTestSuite):
	def test_recovers_from_timestamp_mismatch_and_links_once(self):
		contact = _make_contact("Race LCC")
		customer = _make_customer(f"Race LCC Co {frappe.generate_hash(length=6)}").name
		real_save = contact.save
		calls = {"n": 0}

		def flaky_save(*args, **kwargs):
			calls["n"] += 1
			if calls["n"] == 1:
				raise frappe.exceptions.TimestampMismatchError()
			return real_save(*args, **kwargs)

		with patch.object(contact, "save", side_effect=flaky_save):
			_link_contact_to_customer(contact, customer)

		self.assertEqual(calls["n"], 2)
		fresh = frappe.get_doc("Contact", contact.name)
		matches = [
			link for link in fresh.links if link.link_doctype == "Customer" and link.link_name == customer
		]
		self.assertEqual(len(matches), 1)

	def test_second_call_does_not_duplicate_link(self):
		contact = _make_contact("Dup LCC")
		customer = _make_customer(f"Dup LCC Co {frappe.generate_hash(length=6)}").name
		_link_contact_to_customer(contact, customer)
		_link_contact_to_customer(contact, customer)

		fresh = frappe.get_doc("Contact", contact.name)
		matches = [
			link for link in fresh.links if link.link_doctype == "Customer" and link.link_name == customer
		]
		self.assertEqual(len(matches), 1)
