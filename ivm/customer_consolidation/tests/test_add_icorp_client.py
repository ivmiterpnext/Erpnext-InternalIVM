"""Tests for add/remove iCorp client on the Customer form (icorp_client_link.py)."""

import random
import string
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	add_icorp_client_to_customer,
	lookup_icorp_client,
	remove_icorp_client_from_customer,
)


def _rand_id() -> str:
	return "2" + "".join(random.choices(string.digits, k=5))


def _make_low_privilege_user() -> str:
	email = f"test_add_icorp_{frappe.generate_hash(length=8)}@example.com"
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Low Privilege",
			"send_welcome_email": 0,
			"roles": [{"role": "Projects User"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_customer(suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "_Test Customer Group", "is_group": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Add Client {suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _icorp_payload(client_id, partner_client_id=None):
	return {
		"data": {
			"id": int(client_id),
			"name": f"Test iCorp Client {client_id}",
			"is_active": True,
			"is_partner_client": False,
			"sv_location_count_active": 0,
			"sv_machine_count_active": 0,
			"partner_client_id": int(partner_client_id) if partner_client_id else 0,
		}
	}


class TestAddIcorpClient(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self._cleanup = []

	def tearDown(self):
		for doctype, name in reversed(self._cleanup):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		super().tearDown()

	def _track(self, doctype, name):
		self._cleanup.append((doctype, name))
		return name

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_unknown_id_throws(self, mock_get):
		mock_get.return_value = {"data": None}
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))
		with self.assertRaises(frappe.ValidationError):
			lookup_icorp_client("999999", customer)

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_add_creates_new_link_with_customer_set(self, mock_get):
		client_id = _rand_id()
		mock_get.return_value = _icorp_payload(client_id)
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))

		result = add_icorp_client_to_customer(client_id, customer)
		self._track("iCorp Client Link", client_id)

		self.assertEqual(result["customer"], customer)
		self.assertEqual(frappe.db.get_value("iCorp Client Link", client_id, "customer"), customer)
		self.assertEqual(
			frappe.db.get_value("iCorp Client Link", client_id, "assignment_source"), "Customer form"
		)

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_add_assigns_existing_unassigned_link(self, mock_get):
		client_id = _rand_id()
		mock_get.return_value = _icorp_payload(client_id)
		self._track(
			"iCorp Client Link",
			frappe.get_doc(
				{
					"doctype": "iCorp Client Link",
					"icorp_client_id": client_id,
					"client_name": "Pre-synced",
					"is_active": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name,
		)
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))

		add_icorp_client_to_customer(client_id, customer)

		self.assertEqual(frappe.db.get_value("iCorp Client Link", client_id, "customer"), customer)

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_add_pulls_in_missing_parent(self, mock_get):
		client_id = _rand_id()
		parent_id = _rand_id()

		def side_effect(endpoint):
			if f"Id={parent_id}" in endpoint:
				return _icorp_payload(parent_id)
			return _icorp_payload(client_id, partner_client_id=parent_id)

		mock_get.side_effect = side_effect
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))

		add_icorp_client_to_customer(client_id, customer)
		self._track("iCorp Client Link", client_id)
		self._track("iCorp Client Link", parent_id)

		self.assertTrue(frappe.db.exists("iCorp Client Link", parent_id))
		self.assertEqual(frappe.db.get_value("iCorp Client Link", client_id, "parent_client"), parent_id)

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_add_refuses_when_assigned_to_different_customer(self, mock_get):
		client_id = _rand_id()
		mock_get.return_value = _icorp_payload(client_id)
		customer_a = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))
		customer_b = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))

		add_icorp_client_to_customer(client_id, customer_a)
		self._track("iCorp Client Link", client_id)

		with self.assertRaises(frappe.ValidationError):
			add_icorp_client_to_customer(client_id, customer_b)

		self.assertEqual(frappe.db.get_value("iCorp Client Link", client_id, "customer"), customer_a)

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_remove_clears_customer(self, mock_get):
		client_id = _rand_id()
		mock_get.return_value = _icorp_payload(client_id)
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))

		add_icorp_client_to_customer(client_id, customer)
		self._track("iCorp Client Link", client_id)

		remove_icorp_client_from_customer(client_id, customer)

		self.assertFalse(frappe.db.get_value("iCorp Client Link", client_id, "customer"))

	@patch("ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get")
	def test_remove_refuses_when_not_assigned_to_that_customer(self, mock_get):
		client_id = _rand_id()
		mock_get.return_value = _icorp_payload(client_id)
		customer_a = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))
		customer_b = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))

		add_icorp_client_to_customer(client_id, customer_a)
		self._track("iCorp Client Link", client_id)

		with self.assertRaises(frappe.ValidationError):
			remove_icorp_client_from_customer(client_id, customer_b)

	def test_add_refused_without_required_role(self):
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))
		low_privilege_user = _make_low_privilege_user()
		self._track("User", low_privilege_user)
		original_user = frappe.session.user
		frappe.set_user(low_privilege_user)
		try:
			with self.assertRaises(frappe.PermissionError):
				add_icorp_client_to_customer(_rand_id(), customer)
		finally:
			frappe.set_user(original_user)

	def test_remove_refused_without_required_role(self):
		customer = self._track("Customer", _make_customer(frappe.generate_hash(length=6)))
		low_privilege_user = _make_low_privilege_user()
		self._track("User", low_privilege_user)
		original_user = frappe.session.user
		frappe.set_user(low_privilege_user)
		try:
			with self.assertRaises(frappe.PermissionError):
				remove_icorp_client_from_customer(_rand_id(), customer)
		finally:
			frappe.set_user(original_user)
