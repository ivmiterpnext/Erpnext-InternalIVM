"""Integration tests for ivm.client_portal.utils.home_page"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.utils.home_page import get_website_user_home_page


class TestGetWebsiteUserHomePage(ERPNextTestSuite):
	"""get_website_user_home_page"""

	def test_system_user_returns_none(self):
		"""System User (non-Website User) returns None regardless of roles."""
		result = get_website_user_home_page("Administrator")
		self.assertIsNone(result)

	def test_administrator_explicitly_returns_none(self):
		"""Explicit regression test: Administrator must return None.

		Administrator's roles include every role in the system, so a naive
		role-based check would incorrectly redirect it to the portal dashboard.
		user_type == "Website User" is the correct guard.
		"""
		result = get_website_user_home_page("Administrator")
		self.assertIsNone(result)

	def test_fresh_system_user_returns_none(self):
		"""Fresh System User (not Administrator) also returns None."""
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"sysuser-{frappe.generate_hash(length=6)}@test.local",
				"first_name": "TestSysUser",
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		result = get_website_user_home_page(user.email)
		self.assertIsNone(result)

	def test_website_user_with_service_portal_role_returns_dashboard(self):
		"""Website User with Service Portal User role returns 'dashboard'."""
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"webuser-{frappe.generate_hash(length=6)}@test.local",
				"first_name": "TestWebUser",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		user.add_roles("Service Portal User")

		result = get_website_user_home_page(user.email)
		self.assertEqual(result, "dashboard")

	def test_website_user_without_service_portal_role_returns_none(self):
		"""Website User without Service Portal User role returns None."""
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"webuser-{frappe.generate_hash(length=6)}@test.local",
				"first_name": "TestWebUserNoRole",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		result = get_website_user_home_page(user.email)
		self.assertIsNone(result)
