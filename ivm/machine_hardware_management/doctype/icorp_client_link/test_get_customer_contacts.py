"""Tests for get_customer_contacts (Customer form -> Create new in iCorp dialog).

Pure Frappe data; no iCorp traffic.
"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	get_customer_contacts,
)


def _make_customer(suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "_Test Customer Group", "is_group": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Contacts {suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_contact(
	first_name: str, last_name: str, customer: str, email: str | None, phone: str | None
) -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"last_name": last_name,
			"email_ids": [{"email_id": email, "is_primary": 1}] if email else [],
			"phone_nos": [{"phone": phone, "is_primary_phone": 1}] if phone else [],
			"links": [{"link_doctype": "Customer", "link_name": customer}] if customer else [],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_low_privilege_user() -> str:
	email = f"test_contacts_{frappe.generate_hash(length=8)}@example.com"
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


class TestGetCustomerContacts(ERPNextTestSuite):
	def test_returns_linked_contacts_with_email_and_phone(self):
		uid = frappe.generate_hash(length=6)
		customer = _make_customer(f"Full {uid}")
		full = _make_contact("Ada", f"Full{uid}", customer, f"ada{uid}@example.com", "5551230001")
		bare = _make_contact("Bob", f"Bare{uid}", customer, None, None)
		other_customer = _make_customer(f"Other {uid}")
		_make_contact("Eve", f"Other{uid}", other_customer, f"eve{uid}@example.com", "5551230002")

		result = get_customer_contacts(customer)

		by_name = {r["name"]: r for r in result}
		self.assertEqual(set(by_name), {full, bare})

		full_row = by_name[full]
		self.assertEqual(full_row["display_name"], f"Ada Full{uid}")
		self.assertEqual(full_row["email"], f"ada{uid}@example.com")
		self.assertEqual(full_row["phone"], "5551230001")

		bare_row = by_name[bare]
		self.assertEqual(bare_row["display_name"], f"Bob Bare{uid}")
		self.assertEqual(bare_row["email"], "")
		self.assertEqual(bare_row["phone"], "")

	def test_orphaned_dynamic_link_is_skipped_without_raising(self):
		uid = frappe.generate_hash(length=6)
		customer = _make_customer(f"Orphan {uid}")
		real = _make_contact("Real", f"Orphan{uid}", customer, f"real{uid}@example.com", "5551230003")
		# Second contact's Customer link is repointed to a parent Contact that doesn't exist,
		# reproducing the orphaned Dynamic Link rows found on dev.local.
		source = _make_contact("Ghost", f"Source{uid}", customer, None, None)
		ghost = f"Missing Contact {uid}"
		frappe.db.sql(
			"update `tabDynamic Link` set parent=%s where parent=%s and link_doctype='Customer'",
			(ghost, source),
		)
		self.assertFalse(frappe.db.exists("Contact", ghost))

		result = get_customer_contacts(customer)

		self.assertEqual([r["name"] for r in result], [real])

	def test_customer_with_no_contacts_returns_empty_list(self):
		customer = _make_customer(f"NoContacts {frappe.generate_hash(length=6)}")
		self.assertEqual(get_customer_contacts(customer), [])

	def test_blank_or_unknown_customer_returns_empty_list(self):
		self.assertEqual(get_customer_contacts(""), [])
		self.assertEqual(get_customer_contacts("No Such Customer Anywhere"), [])

	def test_low_privilege_user_rejected(self):
		customer = _make_customer(f"Perm {frappe.generate_hash(length=6)}")
		original_user = frappe.session.user
		frappe.set_user(_make_low_privilege_user())
		try:
			with self.assertRaises(frappe.PermissionError):
				get_customer_contacts(customer)
		finally:
			frappe.set_user(original_user)
