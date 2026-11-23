"""Tests for Customer.icorp_client_ids, the comma-joined cache of active iCorp Client Links
maintained by iCorpClientLink.on_update / on_trash.

Pure Frappe data; no iCorp traffic.
"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	_refresh_icorp_client_ids_cache,
)


def _make_customer(suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "_Test Customer Group", "is_group": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test ICorp Ids {suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _rand_client_id() -> str:
	return str(int(frappe.generate_hash(length=8), 16) % 900_000_000 + 100_000_000)


def _make_link(customer: str | None, is_active: int = 1) -> str:
	client_id = _rand_client_id()
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": client_id,
			"client_name": f"Client {client_id}",
			"is_active": is_active,
			"customer": customer,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _cached(customer: str) -> str:
	return frappe.db.get_value("Customer", customer, "icorp_client_ids") or ""


class TestRefreshIcorpClientIdsCache(ERPNextTestSuite):
	def test_assigning_link_sets_single_id_on_customer(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		link = _make_link(None)
		self.assertEqual(_cached(customer), "")

		doc = frappe.get_doc("iCorp Client Link", link)
		doc.customer = customer
		doc.save(ignore_permissions=True)

		self.assertEqual(_cached(customer), link)

	def test_second_active_link_appends_and_inactive_link_excluded(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		active_a = _make_link(customer, is_active=1)
		active_b = _make_link(customer, is_active=1)
		inactive = _make_link(customer, is_active=0)

		self.assertEqual(_cached(customer), ", ".join(sorted([active_a, active_b])))
		self.assertNotIn(inactive, _cached(customer))

	def test_reassigning_link_updates_both_customers(self):
		cust_a = _make_customer(f"A {frappe.generate_hash(length=6)}")
		cust_b = _make_customer(f"B {frappe.generate_hash(length=6)}")
		link = _make_link(cust_a)
		self.assertEqual(_cached(cust_a), link)
		self.assertEqual(_cached(cust_b), "")

		doc = frappe.get_doc("iCorp Client Link", link)
		doc.customer = cust_b
		doc.save(ignore_permissions=True)

		self.assertEqual(_cached(cust_a), "")
		self.assertEqual(_cached(cust_b), link)

	def test_deleting_link_removes_it_from_customer(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		keep = _make_link(customer)
		gone = _make_link(customer)
		self.assertEqual(_cached(customer), ", ".join(sorted([keep, gone])))

		frappe.delete_doc("iCorp Client Link", gone, ignore_permissions=True)

		self.assertEqual(_cached(customer), keep)

	def test_refresh_with_missing_or_blank_customer_is_noop(self):
		_refresh_icorp_client_ids_cache(None)
		_refresh_icorp_client_ids_cache("")
		_refresh_icorp_client_ids_cache("No Such Customer Anywhere")
