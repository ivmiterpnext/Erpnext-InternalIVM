"""Integration tests for ivm.deployments.services.provision_client_from_deal (contact helpers)"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.provision_client_from_deal import get_primary_contact


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
