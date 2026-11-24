"""Regression tests for ivm.patches.backfill_customer_icorp_client_ids.

Bug: the patch filtered with ["not in", ["", None]]. That compiles to
`customer NOT IN ('', NULL)`, which is NULL (never TRUE) for every row in SQL, so the
backfill matched zero customers whenever any iCorp Client Link had a NULL customer.
Fix: ["is", "set"], which is NULL-safe.
"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.patches import backfill_customer_icorp_client_ids as patch_module


def _make_customer(suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "_Test Customer Group", "is_group": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Backfill ICorp {suffix}",
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


class TestBackfillCustomerIcorpClientIds(ERPNextTestSuite):
	def test_backfill_populates_customer_even_when_unassigned_links_exist(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		link_a = _make_link(customer, is_active=1)
		link_b = _make_link(customer, is_active=1)
		# Literal NULL customer rows: these are what trigger the NOT IN / NULL bug.
		_make_link(None)
		_make_link(None)

		# Simulate pre-backfill state: cache empty even though links exist.
		frappe.db.set_value("Customer", customer, "icorp_client_ids", "")
		self.assertEqual(_cached(customer), "")

		# The patch calls frappe.db.commit(); stub it so rows stay inside the test rollback.
		with patch.object(frappe.db, "commit"):
			patch_module.execute()

		self.assertEqual(_cached(customer), ", ".join(sorted([link_a, link_b])))
