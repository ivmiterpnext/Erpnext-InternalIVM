"""Integration tests for ivm.client_portal.services.provisioning"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.provisioning import ensure_portal_user


def _make_contact(first_name, email=None, is_primary=1, user=None):
	data = {"doctype": "Contact", "first_name": first_name, "user": user}
	if email:
		data["email_ids"] = [{"email_id": email, "is_primary": is_primary}]
	doc = frappe.get_doc(data)
	doc.insert(ignore_permissions=True)
	return doc


class TestEnsurePortalUser(ERPNextTestSuite):
	def test_noop_when_user_already_linked(self):
		contact = _make_contact("Already Linked", email="already@example.com", user="Administrator")
		result = ensure_portal_user(contact.name)
		self.assertEqual(result["status"], "ok")
		self.assertIn("already linked", result["message"].lower())

	def test_error_when_no_email(self):
		contact = _make_contact("No Email Contact")
		result = ensure_portal_user(contact.name)
		self.assertEqual(result["status"], "error")

	def test_creates_user_and_links_contact(self):
		email = f"portal-{frappe.generate_hash(length=6)}@example.com"
		contact = _make_contact("New Portal User", email=email)
		result = ensure_portal_user(contact.name)

		self.assertEqual(result["status"], "ok")
		self.assertTrue(frappe.db.exists("User", email))

		contact.reload()
		self.assertEqual(contact.user, email)

		user_doc = frappe.get_doc("User", email)
		self.assertEqual(user_doc.user_type, "Website User")
		roles = {r.role for r in user_doc.roles}
		self.assertEqual(roles, {"Service Portal User"})

	def test_falls_back_to_first_email_when_none_primary(self):
		email = f"fallback-{frappe.generate_hash(length=6)}@example.com"
		contact = _make_contact("Fallback Email Contact", email=email, is_primary=0)
		result = ensure_portal_user(contact.name)
		self.assertEqual(result["status"], "ok")
		self.assertTrue(frappe.db.exists("User", email))
