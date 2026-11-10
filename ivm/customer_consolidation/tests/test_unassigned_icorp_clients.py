"""Tests for ivm.customer_consolidation.unassigned_icorp_clients"""

import csv
import os
import unittest.mock

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation.unassigned_icorp_clients import (
	find_unassigned_icorp_clients,
	report_unassigned_icorp_clients,
)


def _make_icorp_client_link(icorp_client_id: str, **extra) -> str:
	"""Create an iCorp Client Link record. Returns the icorp_client_id (which is the name)."""
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": icorp_client_id,
			**extra,
		}
	).insert(ignore_permissions=True)
	return doc.name


def _make_customer(name_hint="Cust", **extra) -> str:
	"""Create a Customer record. Returns the customer name."""
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"{name_hint}_{frappe.generate_hash(length=8)}",
			"customer_group": "_Test Customer Group",
			"territory": "All Territories",
			**extra,
		}
	).insert(ignore_permissions=True)
	return doc.name


class TestFindUnassignedIcorpClients(ERPNextTestSuite):
	"""find_unassigned_icorp_clients"""

	def test_unassigned_client_is_included(self):
		"""A Link with blank customer is included."""
		client_id = f"test_unassigned_{frappe.generate_hash(length=8)}"
		link = _make_icorp_client_link(client_id, client_name="Test Client", is_active=1)
		self.addCleanup(
			lambda: frappe.delete_doc("iCorp Client Link", link, force=True, ignore_permissions=True)
		)

		rows = find_unassigned_icorp_clients(sync_first=False)
		matching = [r for r in rows if r["icorp_client_id"] == client_id]
		self.assertEqual(len(matching), 1)
		self.assertIn(matching[0]["customer"], ("", None))

	def test_assigned_client_is_excluded(self):
		"""A Link with a real customer set is excluded."""
		customer = _make_customer("AssignedTest")
		self.addCleanup(lambda: frappe.delete_doc("Customer", customer, force=True, ignore_permissions=True))

		client_id = f"test_assigned_{frappe.generate_hash(length=8)}"
		link = _make_icorp_client_link(client_id, client_name="Test Client", customer=customer)
		self.addCleanup(
			lambda: frappe.delete_doc("iCorp Client Link", link, force=True, ignore_permissions=True)
		)

		rows = find_unassigned_icorp_clients(sync_first=False)
		matching = [r for r in rows if r["icorp_client_id"] == client_id]
		self.assertEqual(len(matching), 0)

	def test_multiple_unassigned_sorted_correctly(self):
		"""Multiple unassigned Links come back sorted is_active desc, client_name asc."""
		# Create mix of active/inactive with different names
		client_ids = []

		# Active, name "Alpha"
		cid1 = f"test_sort_1_{frappe.generate_hash(length=8)}"
		link1 = _make_icorp_client_link(cid1, client_name="Alpha", is_active=1)
		client_ids.append((cid1, link1))

		# Inactive, name "Beta"
		cid2 = f"test_sort_2_{frappe.generate_hash(length=8)}"
		link2 = _make_icorp_client_link(cid2, client_name="Beta", is_active=0)
		client_ids.append((cid2, link2))

		# Active, name "Zebra"
		cid3 = f"test_sort_3_{frappe.generate_hash(length=8)}"
		link3 = _make_icorp_client_link(cid3, client_name="Zebra", is_active=1)
		client_ids.append((cid3, link3))

		# Active, name "Beta"
		cid4 = f"test_sort_4_{frappe.generate_hash(length=8)}"
		link4 = _make_icorp_client_link(cid4, client_name="Beta", is_active=1)
		client_ids.append((cid4, link4))

		for _, link in client_ids:
			self.addCleanup(
				lambda l=link: frappe.delete_doc("iCorp Client Link", l, force=True, ignore_permissions=True)
			)

		rows = find_unassigned_icorp_clients(sync_first=False)

		# Filter to just our test clients
		test_rows = [r for r in rows if r["icorp_client_id"] in [cid for cid, _ in client_ids]]

		# Expected order: is_active desc (1 before 0), then client_name asc
		# Active clients sorted by name: Alpha, Beta, Zebra
		# Then inactive: Beta
		expected_order = [
			cid1,
			cid4,
			cid3,
			cid2,
		]  # Alpha(active), Beta(active), Zebra(active), Beta(inactive)
		actual_order = [r["icorp_client_id"] for r in test_rows]

		self.assertEqual(actual_order, expected_order)

	def test_sync_first_false_skips_sync(self):
		"""sync_first=False does not call sync_icorp_client_links."""
		with unittest.mock.patch("ivm.customer_consolidation.apply.sync_icorp_client_links") as mock_sync:
			find_unassigned_icorp_clients(sync_first=False)
			mock_sync.assert_not_called()

	def test_sync_first_true_calls_sync(self):
		"""sync_first=True calls sync_icorp_client_links once."""
		with unittest.mock.patch("ivm.customer_consolidation.apply.sync_icorp_client_links") as mock_sync:
			mock_sync.return_value = {"total": 0, "created": 0, "updated": 0}
			find_unassigned_icorp_clients(sync_first=True)
			mock_sync.assert_called_once()


class TestReportUnassignedIcorpClients(ERPNextTestSuite):
	"""report_unassigned_icorp_clients"""

	def test_report_writes_csv_with_correct_header(self):
		"""report_unassigned_icorp_clients writes a CSV with the correct header."""
		client_id = f"test_report_header_{frappe.generate_hash(length=8)}"
		link = _make_icorp_client_link(client_id, client_name="Test Client")
		self.addCleanup(
			lambda: frappe.delete_doc("iCorp Client Link", link, force=True, ignore_permissions=True)
		)

		path = report_unassigned_icorp_clients(sync_first=False)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		self.assertTrue(os.path.exists(path))
		with open(path) as f:
			reader = csv.DictReader(f)
			header = reader.fieldnames
			expected_header = [
				"icorp_client_id",
				"client_name",
				"is_active",
				"is_partner_client",
				"parent_client",
				"customer",
				"assignment_source",
				"review_status",
				"match_status",
				"proposed_customer",
				"parent_customer",
				"has_multiple_customer_candidates",
				"duplicate_name_siblings",
				"match_evidence",
			]
			self.assertEqual(header, expected_header)

	def test_report_includes_unassigned_row(self):
		"""report_unassigned_icorp_clients includes unassigned client rows."""
		client_id = f"test_report_row_{frappe.generate_hash(length=8)}"
		link = _make_icorp_client_link(client_id, client_name="Test Client Row")
		self.addCleanup(
			lambda: frappe.delete_doc("iCorp Client Link", link, force=True, ignore_permissions=True)
		)

		path = report_unassigned_icorp_clients(sync_first=False)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			rows = list(reader)
			matching = [r for r in rows if r["icorp_client_id"] == client_id]
			self.assertEqual(len(matching), 1)
			self.assertEqual(matching[0]["icorp_client_id"], client_id)
			self.assertEqual(matching[0]["client_name"], "Test Client Row")

	def test_report_excludes_assigned_clients(self):
		"""report_unassigned_icorp_clients excludes clients with customer assigned."""
		customer = _make_customer("ReportExcludeTest")
		self.addCleanup(lambda: frappe.delete_doc("Customer", customer, force=True, ignore_permissions=True))

		client_id = f"test_report_exclude_{frappe.generate_hash(length=8)}"
		link = _make_icorp_client_link(client_id, client_name="Assigned Client", customer=customer)
		self.addCleanup(
			lambda: frappe.delete_doc("iCorp Client Link", link, force=True, ignore_permissions=True)
		)

		path = report_unassigned_icorp_clients(sync_first=False)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			rows = list(reader)
			matching = [r for r in rows if r["icorp_client_id"] == client_id]
			self.assertEqual(len(matching), 0)

	def test_report_row_count_matches_unassigned_count(self):
		"""report_unassigned_icorp_clients row count matches find_unassigned_icorp_clients."""
		# Create a few unassigned clients
		client_ids = []
		for i in range(3):
			cid = f"test_report_count_{i}_{frappe.generate_hash(length=8)}"
			link = _make_icorp_client_link(cid, client_name=f"Client {i}")
			client_ids.append(link)
			self.addCleanup(
				lambda l=link: frappe.delete_doc("iCorp Client Link", l, force=True, ignore_permissions=True)
			)

		rows = find_unassigned_icorp_clients(sync_first=False)
		test_rows = [r for r in rows if r["icorp_client_id"] in client_ids]

		path = report_unassigned_icorp_clients(sync_first=False)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			csv_rows = list(reader)
			csv_test_rows = [r for r in csv_rows if r["icorp_client_id"] in client_ids]
			self.assertEqual(len(csv_test_rows), len(test_rows))
