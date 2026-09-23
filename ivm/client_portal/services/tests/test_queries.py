"""Integration tests for ivm.client_portal.services.queries"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.queries import deal_contact_query


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


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


def _make_contact(first_name):
	doc = frappe.get_doc({"doctype": "Contact", "first_name": first_name})
	doc.insert(ignore_permissions=True)
	return doc


class TestDealContactQuery(ERPNextTestSuite):
	def test_returns_empty_without_crm_deal_filter(self):
		result = deal_contact_query(
			"Contact",
			"",
			"name",
			0,
			20,
			{},
		)
		self.assertEqual(result, [])

	def test_returns_only_contacts_linked_to_deal(self):
		linked_contact = _make_contact("Linked Contact DCQ")
		unlinked_contact = _make_contact("Unlinked Contact DCQ")
		deal = _make_deal(contacts=[{"contact": linked_contact.name, "is_primary": 1}])

		result = deal_contact_query(
			"Contact",
			"",
			"name",
			0,
			20,
			{"crm_deal": deal.name},
		)
		result_names = {row[0] for row in result}
		self.assertIn(linked_contact.name, result_names)
		self.assertNotIn(unlinked_contact.name, result_names)
