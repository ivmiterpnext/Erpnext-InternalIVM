"""Integration tests for ivm.deployments.event_handlers.deal"""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

_RESOLVE = "ivm.deployments.event_handlers.deal.resolve_deal_customer"
_APPLY = "ivm.deployments.event_handlers.deal.apply_deal_customer"
_PROJECTS = "ivm.deployments.event_handlers.deal.create_projects_from_deal"


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_deal(deal_type=None, customer=None, organization=None):
	uid = frappe.generate_hash(length=8)
	_ensure_deal_status("Qualification")
	return frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"custom_deal_type": deal_type,
			"custom_customer": customer,
			"organization": organization,
			"custom_hubspot_deal_name": f"Test Deal {uid}",
		}
	).insert(ignore_permissions=True)


def _make_location(crm_deal):
	uid = frappe.generate_hash(length=8)
	return frappe.get_doc(
		{
			"doctype": "Deployment Location",
			"location_name": f"Loc {uid}",
			"crm_deal": crm_deal,
		}
	).insert(ignore_permissions=True)


@contextmanager
def _mock_deal_services(projects_rv=None, resolved_customer=None):
	"""Patch the service functions called by deal.on_update.

	Customer resolution helpers and create_projects_from_deal are imported at module
	level in deal.py, so they are patched at the deal module path. Applying the resolved Customer (contact, iCorp, Projects, auto-learn)
	is covered by test_customer_resolution.py, so apply_deal_customer is mocked here.
	"""
	projects_rv = projects_rv if projects_rv is not None else []
	with (
		patch(_RESOLVE, return_value=resolved_customer) as mock_resolve,
		patch(_APPLY) as mock_apply,
		patch(_PROJECTS, return_value=projects_rv) as mock_proj,
	):
		yield {
			"resolve": mock_resolve,
			"apply": mock_apply,
			"projects": mock_proj,
		}


class TestDealOnUpdate(ERPNextTestSuite):
	"""on_update event handler for CRM Deal"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Company", "IVM"):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": "IVM",
					"abbr": "IVM",
					"default_currency": "USD",
					"country": "United States",
				}
			).insert(ignore_permissions=True)

	def test_noop_when_status_not_won(self):
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)

		with _mock_deal_services() as mocks:
			deal.custom_hubspot_deal_name = "Updated"
			deal.save(ignore_permissions=True)

			mocks["resolve"].assert_not_called()
			mocks["apply"].assert_not_called()
			mocks["projects"].assert_not_called()

	def test_noop_when_status_unchanged(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)

		frappe.db.set_value("CRM Deal", deal.name, "status", "Won")
		deal.reload()

		with _mock_deal_services() as mocks:
			deal.custom_hubspot_deal_name = "Re-saved"
			deal.save(ignore_permissions=True)

			mocks["resolve"].assert_not_called()
			mocks["projects"].assert_not_called()

	def test_won_without_deployment_location_does_not_raise_and_persists(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		error_logs_before = frappe.db.count("Error Log")

		with _mock_deal_services() as mocks:
			deal.status = "Won"
			with patch("frappe.msgprint") as mock_msg:
				deal.save(ignore_permissions=True)

			# (1) no raise (reaching here proves it), (4) project creation still invoked, creates nothing
			mocks["projects"].assert_called_once_with(deal.name)
			matching = [
				c for c in mock_msg.call_args_list if c.kwargs.get("title") == "No Deployment Locations"
			]
			self.assertTrue(matching)

		# (2) the status change is persisted, not rolled back
		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "status"), "Won")
		# (3) an Error Log entry was created
		self.assertGreater(frappe.db.count("Error Log"), error_logs_before)
		self.assertTrue(
			frappe.get_all(
				"Error Log",
				filters={"method": ["like", f"%{deal.name}%"]},
				limit=1,
			)
		)

	def test_resolved_customer_applied_on_won_new_business(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)

		with _mock_deal_services(resolved_customer="CUST-RESOLVED") as mocks:
			deal.status = "Won"
			deal.save(ignore_permissions=True)

			mocks["resolve"].assert_called_once()
			mocks["apply"].assert_called_once_with(deal.name, "CUST-RESOLVED")

	def test_resolved_customer_applied_on_won_existing_business(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="Existing Business")
		_make_location(deal.name)

		with _mock_deal_services(resolved_customer="CUST-EXISTING") as mocks:
			deal.status = "Won"
			deal.save(ignore_permissions=True)

			mocks["apply"].assert_called_once_with(deal.name, "CUST-EXISTING")

	def test_unresolved_won_deal_creates_no_tasks(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)
		tasks_before = frappe.db.count("Task")

		with _mock_deal_services(resolved_customer=None) as mocks:
			deal.status = "Won"
			deal.save(ignore_permissions=True)

			mocks["apply"].assert_not_called()
			mocks["projects"].assert_called_once()
		self.assertEqual(frappe.db.count("Task"), tasks_before)

	def test_customer_resolution_failure_logged_not_raised(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)

		with _mock_deal_services() as mocks:
			mocks["resolve"].side_effect = ValueError("Simulated resolution failure")
			with patch("frappe.log_error") as mock_log:
				deal.status = "Won"
				deal.save(ignore_permissions=True)

			titles = [c.kwargs.get("title", "") for c in mock_log.call_args_list]
			self.assertTrue(any("Customer resolution failed" in t for t in titles))
			mocks["projects"].assert_called_once()

	def test_project_creation_failure_logged_not_raised(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)

		with _mock_deal_services() as mocks:
			mocks["projects"].side_effect = Exception("Simulated failure")
			with patch("frappe.log_error") as mock_log:
				deal.status = "Won"
				deal.save(ignore_permissions=True)

			error_titles = [c.kwargs.get("title", "") for c in mock_log.call_args_list]
			self.assertTrue(any("Failed to create Deployments" in t for t in error_titles))

	def test_msgprint_on_successful_project_creation(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)

		with _mock_deal_services(projects_rv=["PROJ-0001"]):
			with patch("frappe.msgprint") as mock_msg:
				deal.status = "Won"
				deal.save(ignore_permissions=True)

			matching = [c for c in mock_msg.call_args_list if "Created 1 deployment(s)" in str(c)]
			self.assertTrue(matching)
