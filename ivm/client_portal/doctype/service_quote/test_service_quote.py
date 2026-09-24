"""Integration tests for ivm.client_portal.doctype.service_quote.service_quote"""

from unittest.mock import patch

import frappe
from frappe.utils import add_days, today

from ivm.client_portal.doctype.service_quote.service_quote import has_website_permission

TEST_USER_1 = "test@example.com"


def _make_contact(first_name, user=None):
	contact = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"user": user,
		}
	)
	contact.insert(ignore_permissions=True)
	return contact


def _make_quote(top_contact_name, signers=None):
	doc = frappe.get_doc(
		{
			"doctype": "Service Quote",
			"contact": top_contact_name,
			"sales_representative": "Administrator",
			"customer": "_Test Customer",
			"signers": signers or [],
		}
	)
	doc.insert(ignore_permissions=True)
	with patch("ivm.client_portal.event_handlers.service_quote.on_submit"):
		doc.submit()
	frappe.db.set_value("Service Quote", doc.name, "status", "Sent")
	doc.reload()
	return doc


class TestHasWebsitePermission:
	"""has_website_permission"""

	def test_guest_is_denied(self):
		top_contact = _make_contact("Top Contact HWP Guest")
		quote = _make_quote(top_contact.name)
		self.assertFalse(has_website_permission(quote, "read", "Guest"))

	def test_denied_when_user_has_no_linked_contact(self):
		top_contact = _make_contact("Top Contact HWP Orphan")
		quote = _make_quote(top_contact.name)
		self.assertFalse(has_website_permission(quote, "read", "no-such-user@example.com"))

	def test_denied_when_contact_not_a_signer(self):
		top_contact = _make_contact("Top Contact HWP NotSigner")
		signer_contact = _make_contact("Signer Contact HWP NotSigner", user="Administrator")
		quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
		self.assertFalse(has_website_permission(quote, "read", TEST_USER_1))

	def test_allowed_when_contact_is_signer(self):
		top_contact = _make_contact("Top Contact HWP Allowed")
		signer_contact = _make_contact("Signer Contact HWP Allowed", user="Administrator")
		quote = _make_quote(top_contact.name, signers=[{"contact": signer_contact.name}])
		self.assertTrue(has_website_permission(quote, "read", "Administrator"))


def _make_organization(name_hint="Org"):
	doc = frappe.get_doc(
		{
			"doctype": "CRM Organization",
			"organization_name": f"{name_hint} {frappe.generate_hash(length=8)}",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_deal(deal_type=None, organization=None, customer=None, deal_owner="Administrator"):
	"""Note: Service Quote.sales_representative has fetch_from="crm_deal.deal_owner",
	so deal_owner must be set here or an explicit sales_representative on a linked
	quote gets silently overwritten to blank by Frappe's fetch-from mechanism during
	validate(), tripping the mandatory check."""
	_ensure_deal_status("Qualification")
	return frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"custom_deal_type": deal_type,
			"organization": organization,
			"custom_customer": customer,
			"deal_owner": deal_owner,
			"custom_hubspot_deal_name": f"Test Deal {frappe.generate_hash(length=8)}",
		}
	).insert(ignore_permissions=True)


def _make_draft_quote(**overrides):
	"""Insert a draft (unsubmitted) Service Quote. Defaults customer to
	"_Test Customer" to satisfy the mutual-exclusivity invariant unless
	the caller explicitly overrides customer/crm_organization."""
	top_contact = _make_contact(f"Contact {frappe.generate_hash(length=6)}")
	data = {
		"doctype": "Service Quote",
		"contact": top_contact.name,
		"sales_representative": "Administrator",
		"customer": "_Test Customer",
	}
	data.update(overrides)
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)
	return doc


class TestBeforeInsertValidUntil:
	"""before_insert: valid_until default"""

	def test_defaults_to_30_days_when_unset(self):
		doc = _make_draft_quote()
		self.assertEqual(doc.valid_until, add_days(today(), 30))

	def test_not_overridden_when_provided(self):
		explicit = add_days(today(), 5)
		doc = _make_draft_quote(valid_until=explicit)
		self.assertEqual(doc.valid_until, explicit)


class TestComputeItemAmounts:
	"""validate: _compute_item_amounts"""

	def test_amount_computed_from_qty_and_rate(self):
		doc = _make_draft_quote(items=[{"description": "Item A", "qty": 3, "rate": 10}])
		self.assertEqual(doc.items[0].amount, 30)

	def test_stale_amount_overwritten(self):
		doc = _make_draft_quote(items=[{"description": "Item B", "qty": 2, "rate": 5, "amount": 999}])
		self.assertEqual(doc.items[0].amount, 10)

	def test_zero_qty_treated_as_zero(self):
		doc = _make_draft_quote(items=[{"description": "Item C", "qty": 0, "rate": 10}])
		self.assertEqual(doc.items[0].amount, 0)

	def test_zero_rate_treated_as_zero(self):
		doc = _make_draft_quote(items=[{"description": "Item D", "qty": 5, "rate": 0}])
		self.assertEqual(doc.items[0].amount, 0)


class TestComputeGrandTotal:
	"""validate: _compute_grand_total"""

	def test_sums_all_item_amounts(self):
		doc = _make_draft_quote(
			items=[
				{"description": "A", "qty": 2, "rate": 5},
				{"description": "B", "qty": 1, "rate": 7},
			]
		)
		self.assertEqual(doc.grand_total, 17)

	def test_zero_with_no_items(self):
		doc = _make_draft_quote(items=[])
		self.assertEqual(doc.grand_total, 0)

	def test_recomputed_on_second_save(self):
		doc = _make_draft_quote(items=[{"description": "A", "qty": 2, "rate": 5}])
		self.assertEqual(doc.grand_total, 10)
		doc.append("items", {"description": "B", "qty": 1, "rate": 7})
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.grand_total, 17)


class TestResolveCustomerOrOrganization:
	"""validate: _resolve_customer_or_organization"""

	def test_new_business_sets_organization_clears_customer(self):
		org = _make_organization("NewBiz")
		deal = _make_deal(deal_type="New Business", organization=org.name)
		doc = _make_draft_quote(crm_deal=deal.name)
		self.assertEqual(doc.crm_organization, org.name)
		self.assertFalse(doc.customer)

	def test_existing_business_sets_customer_clears_organization(self):
		deal = _make_deal(deal_type="Existing Business", customer="_Test Customer")
		doc = _make_draft_quote(crm_deal=deal.name)
		self.assertEqual(doc.customer, "_Test Customer")
		self.assertFalse(doc.crm_organization)

	def test_switching_crm_deal_re_resolves(self):
		org_a = _make_organization("OrgA")
		deal_a = _make_deal(deal_type="New Business", organization=org_a.name)
		doc = _make_draft_quote(crm_deal=deal_a.name)
		self.assertEqual(doc.crm_organization, org_a.name)

		deal_b = _make_deal(deal_type="Existing Business", customer="_Test Customer")
		doc.crm_deal = deal_b.name
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.customer, "_Test Customer")
		self.assertFalse(doc.crm_organization)

	def test_resolution_skipped_when_crm_deal_unchanged_despite_drift(self):
		org_a = _make_organization("OrgDrift")
		deal_a = _make_deal(deal_type="New Business", organization=org_a.name)
		doc = _make_draft_quote(crm_deal=deal_a.name)
		self.assertEqual(doc.crm_organization, org_a.name)

		# Simulate the underlying deal drifting to Existing Business after
		# quote creation, without touching the quote's crm_deal field itself.
		frappe.db.set_value("CRM Deal", deal_a.name, "custom_deal_type", "Existing Business")

		doc.terms = "Updated terms only"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.crm_organization, org_a.name)  # unchanged, not re-derived
		self.assertFalse(doc.customer)

	def test_mutual_exclusivity_throws_when_both_set(self):
		org = _make_organization("BothSet")
		with self.assertRaises(frappe.ValidationError):
			_make_draft_quote(customer="_Test Customer", crm_organization=org.name)

	def test_mutual_exclusivity_throws_when_neither_set(self):
		with self.assertRaises(frappe.ValidationError):
			_make_draft_quote(customer=None, crm_organization=None)
