"""Integration tests for ivm.deployments.services.provision_client_from_deal (contact helpers)"""

from unittest.mock import MagicMock, patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.provision_client_from_deal import (
	_link_contact_to_customer,
	get_primary_contact,
)
from ivm.integrations.hubspot.constants import CONTACT_TYPE_ID
from ivm.integrations.hubspot.sync_utils import SyncLockBusy


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

	def test_lock_busy_propagates_sync_lock_busy_and_does_not_save(self):
		contact = _make_contact("Locked LCC")
		contact.custom_hubspot_contact_id = "900001"
		customer = _make_customer(f"Locked LCC Co {frappe.generate_hash(length=6)}").name
		lock = MagicMock()
		lock.acquire.return_value = False

		with patch.object(frappe.cache, "lock", return_value=lock) as lock_factory:
			with patch("ivm.deployments.services.provision_client_from_deal.save_doc") as save_mock:
				with self.assertRaises(SyncLockBusy) as ctx:
					_link_contact_to_customer(contact, customer)

		self.assertEqual(ctx.exception.object_type_id, CONTACT_TYPE_ID)
		self.assertEqual(ctx.exception.object_id, "900001")
		lock_factory.assert_called_once()
		lock.acquire.assert_called_once()
		lock.release.assert_not_called()
		save_mock.assert_not_called()

	def test_locks_and_releases_around_link_when_hubspot_id_set(self):
		contact = _make_contact("Locked OK LCC")
		contact.custom_hubspot_contact_id = "900002"
		customer = _make_customer(f"Locked OK LCC Co {frappe.generate_hash(length=6)}").name
		lock = MagicMock()
		lock.acquire.return_value = True
		call_order = []
		lock.acquire.side_effect = lambda: call_order.append("acquire") or True
		lock.release.side_effect = lambda: call_order.append("release")

		with patch.object(frappe.cache, "lock", return_value=lock) as lock_factory:
			_link_contact_to_customer(contact, customer)

		lock_factory.assert_called_once()
		lock_key = lock_factory.call_args.args[0]
		if isinstance(lock_key, bytes):
			lock_key = lock_key.decode()
		self.assertIn(f"hubspot_sync_lock:{CONTACT_TYPE_ID}:900002", lock_key)
		self.assertEqual(call_order, ["acquire", "release"])

		fresh = frappe.get_doc("Contact", contact.name)
		matches = [
			link for link in fresh.links if link.link_doctype == "Customer" and link.link_name == customer
		]
		self.assertEqual(len(matches), 1)

	def test_no_lock_attempted_when_contact_has_no_hubspot_id(self):
		contact = _make_contact("Non-HS LCC")
		customer = _make_customer(f"Non-HS LCC Co {frappe.generate_hash(length=6)}").name

		with patch.object(frappe.cache, "lock") as lock_factory:
			_link_contact_to_customer(contact, customer)

		lock_factory.assert_not_called()
		fresh = frappe.get_doc("Contact", contact.name)
		matches = [
			link for link in fresh.links if link.link_doctype == "Customer" and link.link_name == customer
		]
		self.assertEqual(len(matches), 1)
