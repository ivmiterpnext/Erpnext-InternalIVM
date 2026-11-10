"""Tests for ivm.customer_consolidation.customer_form"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation.customer_form import load_icorp_clients
from ivm.customer_consolidation.tests.test_apply import _make_customer, _make_icorp_client_link


def _load(customer_name):
	doc = frappe.get_doc("Customer", customer_name)
	load_icorp_clients(doc)
	onload = doc.get("__onload") or {}
	return onload.get("icorp_clients") or [], onload.get("icorp_managed_clients") or []


class TestLoadIcorpClients(ERPNextTestSuite):
	def test_standalone_client_with_no_children(self):
		customer = _make_customer("Standalone")
		link = _make_icorp_client_link(customer=customer.name)

		clients, managed = _load(customer.name)

		row = next(c for c in clients if c["name"] == link.name)
		self.assertEqual(row["relationship"], "Standalone")
		self.assertIn("partner_customer", row)
		self.assertIn("partner_icorp_client_id", row)
		self.assertEqual(managed, [])

	def test_master_partner_and_unassigned_children(self):
		owner = _make_customer("Owner")
		other = _make_customer("EndCustomer")
		master = _make_icorp_client_link(customer=owner.name)
		location = _make_icorp_client_link(customer=owner.name, parent_client=master.name)
		managed_child = _make_icorp_client_link(customer=other.name, parent_client=master.name)
		unassigned_child = _make_icorp_client_link(parent_client=master.name)

		clients, managed = _load(owner.name)

		master_row = next(c for c in clients if c["name"] == master.name)
		self.assertEqual(
			master_row["relationship"],
			"Master of 1 location; Partner: manages 1 client for other Customers; 1 child client unassigned",
		)
		location_row = next(c for c in clients if c["name"] == location.name)
		self.assertTrue(location_row["relationship"].startswith("Location of"))

		managed_names = {m["name"]: m for m in managed}
		self.assertEqual(set(managed_names), {managed_child.name, unassigned_child.name})
		self.assertEqual(managed_names[managed_child.name]["customer"], other.name)
		self.assertEqual(managed_names[unassigned_child.name]["customer"], "")

	def test_partner_flag_appended(self):
		customer = _make_customer("FlaggedPartner")
		link = _make_icorp_client_link(customer=customer.name)
		frappe.db.set_value("iCorp Client Link", link.name, "is_partner_client", 1)

		clients, _ = _load(customer.name)

		row = next(c for c in clients if c["name"] == link.name)
		self.assertEqual(row["relationship"], "Standalone (flagged partner in iCorp)")
