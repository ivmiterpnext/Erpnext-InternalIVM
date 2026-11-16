"""Tests for ivm.deployments.patches.backfill_project_icorp_client.run_backfill"""

import random
import string
from unittest import mock

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.patches.backfill_project_icorp_client import run_backfill


def _rand_id() -> str:
	"""Random 6-digit numeric string, safe for iCorp Client Link's field:icorp_client_id autoname."""
	return "".join(random.choices(string.digits, k=6))


def _make_customer(name_suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": "_Test Customer Group",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Customer {name_suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def _make_client(icorp_client_id, customer=None, parent_client=None):
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": icorp_client_id,
			"client_name": f"Test Client {icorp_client_id}",
			"customer": customer,
			"parent_client": parent_client,
			"is_active": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_legacy_project(customer, client_id):
	"""Deployment Project with legacy client_id set and icorp_client_id blank (pre-backfill state)."""
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"Test Backfill {frappe.generate_hash(length=8)}",
			"project_type": "Deployment",
			"customer": customer,
			"client_id": client_id,
		}
	)
	doc.flags.ignore_validate = True
	doc.insert(ignore_permissions=True, ignore_mandatory=True)
	return doc.name


class TestRunBackfill(ERPNextTestSuite):
	def test_derived_partner_equal_to_project_customer_leaves_partner_blank(self):
		uid = frappe.generate_hash(length=6)
		partner_customer = _make_customer(f"BfPartnerEq {uid}")
		end_customer = _make_customer(f"BfEndEq {uid}")
		parent = _make_client(_rand_id(), customer=partner_customer)
		child = _make_client(_rand_id(), customer=end_customer, parent_client=parent)
		# Project's own customer is the partner, so the derived partner equals it and is discarded.
		project = _make_legacy_project(partner_customer, child)

		run_backfill()

		row = frappe.db.get_value("Project", project, ["icorp_client_id", "partner_customer"], as_dict=True)
		self.assertEqual(row.icorp_client_id, child)
		self.assertFalse(row.partner_customer)

	def test_parent_customer_different_sets_partner_customer(self):
		uid = frappe.generate_hash(length=6)
		partner_customer = _make_customer(f"BfPartner {uid}")
		end_customer = _make_customer(f"BfEnd {uid}")
		parent = _make_client(_rand_id(), customer=partner_customer)
		child = _make_client(_rand_id(), customer=end_customer, parent_client=parent)
		project = _make_legacy_project(end_customer, child)

		run_backfill()

		row = frappe.db.get_value(
			"Project", project, ["icorp_client_id", "partner_customer", "customer"], as_dict=True
		)
		self.assertEqual(row.icorp_client_id, child)
		self.assertEqual(row.customer, end_customer)
		self.assertEqual(row.partner_customer, partner_customer)

	def test_runs_when_custom_master_customer_column_absent(self):
		"""Simulates the missing column by patching frappe.db.has_column; no DDL is executed."""
		uid = frappe.generate_hash(length=6)
		partner_customer = _make_customer(f"BfNoCol {uid}")
		end_customer = _make_customer(f"BfNoColEnd {uid}")
		parent = _make_client(_rand_id(), customer=partner_customer)
		child = _make_client(_rand_id(), customer=end_customer, parent_client=parent)
		project = _make_legacy_project(end_customer, child)

		real_has_column = frappe.db.has_column

		def fake_has_column(doctype, column):
			if doctype == "Project" and column == "custom_master_customer":
				return False
			return real_has_column(doctype, column)

		with mock.patch.object(frappe.db, "has_column", side_effect=fake_has_column):
			run_backfill()

		row = frappe.db.get_value("Project", project, ["icorp_client_id", "partner_customer"], as_dict=True)
		self.assertEqual(row.icorp_client_id, child)
		self.assertEqual(row.partner_customer, partner_customer)
