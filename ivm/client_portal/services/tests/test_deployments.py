"""Integration tests for ivm.client_portal.services.deployments"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.deployments import get_deployments_for_user

TEST_USER = "test@example.com"


def _make_contact_for_user(user, customer=None):
	doc = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": f"Contact {frappe.generate_hash(length=6)}",
			"user": user,
		}
	)
	doc.insert(ignore_permissions=True)
	if customer:
		doc.append("links", {"link_doctype": "Customer", "link_name": customer})
		doc.save(ignore_permissions=True)
	return doc


def _make_customer():
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": frappe.generate_hash(length=10),
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestGetDeploymentsForUser(ERPNextTestSuite):
	def test_no_contact_returns_empty_list(self):
		self.assertEqual(get_deployments_for_user("no-such-user@example.com"), [])

	def test_no_linked_customer_returns_empty_list(self):
		_make_contact_for_user(TEST_USER)
		self.assertEqual(get_deployments_for_user(TEST_USER), [])

	def test_returns_deployment_projects_for_linked_customer(self):
		customer = _make_customer()
		_make_contact_for_user(TEST_USER, customer=customer.name)
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Deploy {frappe.generate_hash(length=6)}",
				"customer": customer.name,
				"company": "_Test Company",
				"project_type": "Deployment",
			}
		)
		project.insert(ignore_permissions=True)

		result = get_deployments_for_user(TEST_USER)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["name"], project.name)

	def test_non_deployment_project_type_excluded(self):
		customer = _make_customer()
		_make_contact_for_user(TEST_USER, customer=customer.name)
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Internal {frappe.generate_hash(length=6)}",
				"customer": customer.name,
				"company": "_Test Company",
				"project_type": "Internal",
			}
		)
		project.insert(ignore_permissions=True)

		result = get_deployments_for_user(TEST_USER)
		self.assertEqual(result, [])
