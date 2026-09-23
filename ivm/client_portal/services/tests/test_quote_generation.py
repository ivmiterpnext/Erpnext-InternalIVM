"""Integration tests for ivm.client_portal.services.quote_generation"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.quote_generation import (
	create_service_quote_from_deal,
	get_deal_primary_contact,
)


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_contact(first_name):
	doc = frappe.get_doc({"doctype": "Contact", "first_name": first_name})
	doc.insert(ignore_permissions=True)
	return doc


def _make_deal(deal_owner="Administrator", contacts=None):
	"""custom_deal_type/custom_customer must be set so ServiceQuote's own
	_resolve_customer_or_organization() validate hook (which runs whenever
	crm_deal is set) can populate customer/crm_organization -- otherwise
	neither gets set and the mutual-exclusivity check throws."""
	_ensure_deal_status("Qualification")
	return frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"deal_owner": deal_owner,
			"custom_deal_type": "Existing Business",
			"custom_customer": "_Test Customer",
			"contacts": contacts or [],
			"custom_hubspot_deal_name": f"Test Deal {frappe.generate_hash(length=8)}",
		}
	).insert(ignore_permissions=True)


def _make_location(deal_name, **table_rows):
	"""table_rows maps child-table fieldname (e.g. smartstation_details) to a
	list of row dicts. Deployment Location's own validate() hook
	(_update_device_quantities) always recalculates number_of_machines etc.
	from actual child-table row counts -- setting those quantity fields
	directly has no effect, rows must be provided instead."""
	data = {
		"doctype": "Deployment Location",
		"location_name": f"Loc {frappe.generate_hash(length=8)}",
		"crm_deal": deal_name,
	}
	data.update(table_rows)
	return frappe.get_doc(data).insert(ignore_permissions=True)


class TestGetDealPrimaryContact(ERPNextTestSuite):
	def test_returns_primary_contact_name(self):
		contact = _make_contact("Primary Contact GDPC")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 1}])
		self.assertEqual(get_deal_primary_contact(deal.name), contact.name)

	def test_returns_none_when_no_contacts(self):
		deal = _make_deal(contacts=[])
		self.assertIsNone(get_deal_primary_contact(deal.name))

	def test_falls_back_to_first_contact_when_none_marked_primary(self):
		contact = _make_contact("Only Contact GDPC")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 0}])
		self.assertEqual(get_deal_primary_contact(deal.name), contact.name)


class TestCreateServiceQuoteFromDeal(ERPNextTestSuite):
	def test_throws_when_no_primary_contact(self):
		deal = _make_deal(contacts=[])
		with self.assertRaises(frappe.ValidationError):
			create_service_quote_from_deal(deal.name)

	def test_throws_when_no_deal_owner(self):
		contact = _make_contact("Contact NoOwner")
		deal = _make_deal(deal_owner=None, contacts=[{"contact": contact.name, "is_primary": 1}])
		with self.assertRaises(frappe.ValidationError):
			create_service_quote_from_deal(deal.name)

	def test_creates_quote_with_items_for_positive_counts(self):
		contact = _make_contact("Contact WithItems")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 1}])
		_make_location(
			deal.name,
			smartstation_details=[{"machine_name": "M1"}, {"machine_name": "M2"}, {"machine_name": "M3"}],
			smartvault_details=[{"machine_name": "V1"}],
		)

		result = create_service_quote_from_deal(deal.name)
		quote = frappe.get_doc("Service Quote", result["service_quote"])

		self.assertEqual(quote.contact, contact.name)
		self.assertEqual(quote.sales_representative, "Administrator")
		self.assertEqual(len(quote.items), 2)
		descriptions = {item.description for item in quote.items}
		self.assertTrue(any("SmartStation" in d for d in descriptions))
		self.assertTrue(any("SmartVault" in d for d in descriptions))
		self.assertNotIn("warning", result)

	def test_zero_count_equipment_types_excluded(self):
		contact = _make_contact("Contact ZeroCounts")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 1}])
		_make_location(deal.name)

		result = create_service_quote_from_deal(deal.name)
		quote = frappe.get_doc("Service Quote", result["service_quote"])
		self.assertEqual(len(quote.items), 0)
		self.assertIn("warning", result)

	def test_no_locations_returns_warning_with_empty_quote(self):
		contact = _make_contact("Contact NoLocations")
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 1}])

		result = create_service_quote_from_deal(deal.name)
		self.assertIn("warning", result)
		quote = frappe.get_doc("Service Quote", result["service_quote"])
		self.assertEqual(len(quote.items), 0)
