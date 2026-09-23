"""Integration tests for ivm.deployments.event_handlers.project"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from frappe.utils import getdate

from ivm.deployments.utils.date_calculations import add_business_days


def _ensure_deal_status(status):
	"""Ensure a CRM Deal Status record exists."""
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_deal(custom_hubspot_deal_id=None):
	"""Create and insert a CRM Deal with optional custom_hubspot_deal_id."""
	_ensure_deal_status("Qualification")
	uid = frappe.generate_hash(length=8)
	return frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"custom_hubspot_deal_name": f"Test Deal {uid}",
			"custom_hubspot_deal_id": custom_hubspot_deal_id or f"hubspot_{uid}",
		}
	).insert(ignore_permissions=True)


def _make_project(
	project_name=None,
	placement_agreement=None,
	expedited_delivery=False,
	locale="Domestic",
	added_days=0,
	status=None,
	custom_hubspot_deal_id=None,
	custom_crm_deal=None,
):
	"""Create and insert a Project with specified parameters."""
	if not project_name:
		project_name = f"Test Project {frappe.generate_hash(length=8)}"

	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"placement_agreement": placement_agreement,
			"expedited_delivery": 1 if expedited_delivery else 0,
			"locale": locale,
			"added_days": added_days,
			"status": status or "Open",
			"custom_hubspot_deal_id": custom_hubspot_deal_id,
			"custom_crm_deal": custom_crm_deal,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestUpdateDueDates(ERPNextTestSuite):
	"""Test _update_due_dates function and due-date field calculation."""

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

	def test_no_placement_agreement_clears_all_fields(self):
		"""When placement_agreement is empty, all 9 due-date fields are None."""
		doc = _make_project(placement_agreement=None)
		doc.reload()

		self.assertIsNone(doc.provide_planogram_due)
		self.assertIsNone(doc.approve_planogram_and_locker_config_due)
		self.assertIsNone(doc.pog_created_in_database_due)
		self.assertIsNone(doc.sample_products_due)
		self.assertIsNone(doc.sample_badge_due)
		self.assertIsNone(doc.delivery_and_install_contact_due_customs)
		self.assertIsNone(doc.delivery_install_and_coi_requirements)
		self.assertIsNone(doc.user_and_restriction_requirements_due)
		self.assertIsNone(doc.graphic_design_approval_due)

	def test_domestic_not_expedited_uses_domestic_days(self):
		"""Domestic, non-expedited Project uses domestic_days for each field."""
		placement = "2024-01-08"  # Monday
		doc = _make_project(
			placement_agreement=placement,
			expedited_delivery=False,
			locale="Domestic",
			added_days=0,
		)
		doc.reload()

		# Verify each field matches the expected domestic_days value
		expected_provide_planogram = add_business_days(placement, 17)
		self.assertEqual(getdate(doc.provide_planogram_due), getdate(expected_provide_planogram))

		expected_approve_planogram = add_business_days(placement, 24)
		self.assertEqual(
			getdate(doc.approve_planogram_and_locker_config_due), getdate(expected_approve_planogram)
		)

		expected_pog_created = add_business_days(placement, 25)
		self.assertEqual(getdate(doc.pog_created_in_database_due), getdate(expected_pog_created))

		expected_sample_products = add_business_days(placement, 7)
		self.assertEqual(getdate(doc.sample_products_due), getdate(expected_sample_products))

		expected_sample_badge = add_business_days(placement, 7)
		self.assertEqual(getdate(doc.sample_badge_due), getdate(expected_sample_badge))

		expected_delivery_contact = add_business_days(placement, 10)
		self.assertEqual(
			getdate(doc.delivery_and_install_contact_due_customs), getdate(expected_delivery_contact)
		)

		expected_coi = add_business_days(placement, 10)
		self.assertEqual(getdate(doc.delivery_install_and_coi_requirements), getdate(expected_coi))

		expected_user_restriction = add_business_days(placement, 20)
		self.assertEqual(
			getdate(doc.user_and_restriction_requirements_due), getdate(expected_user_restriction)
		)

		expected_graphic = add_business_days(placement, 20)
		self.assertEqual(getdate(doc.graphic_design_approval_due), getdate(expected_graphic))

	def test_international_not_expedited_uses_international_days(self):
		"""International, non-expedited Project uses international_days for each field."""
		placement = "2024-01-08"  # Monday
		doc = _make_project(
			placement_agreement=placement,
			expedited_delivery=False,
			locale="International",
			added_days=0,
		)
		doc.reload()

		# Verify each field matches the expected international_days value
		expected_provide_planogram = add_business_days(placement, 23)
		self.assertEqual(getdate(doc.provide_planogram_due), getdate(expected_provide_planogram))

		expected_approve_planogram = add_business_days(placement, 27)
		self.assertEqual(
			getdate(doc.approve_planogram_and_locker_config_due), getdate(expected_approve_planogram)
		)

		expected_pog_created = add_business_days(placement, 31)
		self.assertEqual(getdate(doc.pog_created_in_database_due), getdate(expected_pog_created))

		expected_sample_products = add_business_days(placement, 13)
		self.assertEqual(getdate(doc.sample_products_due), getdate(expected_sample_products))

		expected_sample_badge = add_business_days(placement, 13)
		self.assertEqual(getdate(doc.sample_badge_due), getdate(expected_sample_badge))

		expected_delivery_contact = add_business_days(placement, 10)
		self.assertEqual(
			getdate(doc.delivery_and_install_contact_due_customs), getdate(expected_delivery_contact)
		)

		expected_coi = add_business_days(placement, 10)
		self.assertEqual(getdate(doc.delivery_install_and_coi_requirements), getdate(expected_coi))

		expected_user_restriction = add_business_days(placement, 20)
		self.assertEqual(
			getdate(doc.user_and_restriction_requirements_due), getdate(expected_user_restriction)
		)

		expected_graphic = add_business_days(placement, 20)
		self.assertEqual(getdate(doc.graphic_design_approval_due), getdate(expected_graphic))

	def test_expedited_ignores_locale(self):
		"""Expedited Project uses expedited_days regardless of locale."""
		placement = "2024-01-08"  # Monday

		# Create expedited Domestic
		doc_domestic = _make_project(
			placement_agreement=placement,
			expedited_delivery=True,
			locale="Domestic",
			added_days=0,
		)
		doc_domestic.reload()

		# Create expedited International
		doc_intl = _make_project(
			placement_agreement=placement,
			expedited_delivery=True,
			locale="International",
			added_days=0,
		)
		doc_intl.reload()

		# Both should use expedited_days (7, 11, 10, 2, 2, 9, 9, 14, 9)
		self.assertEqual(
			getdate(doc_domestic.provide_planogram_due),
			getdate(doc_intl.provide_planogram_due),
		)
		self.assertEqual(
			getdate(doc_domestic.approve_planogram_and_locker_config_due),
			getdate(doc_intl.approve_planogram_and_locker_config_due),
		)
		self.assertEqual(
			getdate(doc_domestic.pog_created_in_database_due),
			getdate(doc_intl.pog_created_in_database_due),
		)

	def test_added_days_shifts_all_fields(self):
		"""added_days shifts every field by exactly that many additional business days."""
		placement = "2024-01-08"  # Monday

		# Create with added_days=0
		doc_base = _make_project(
			placement_agreement=placement,
			expedited_delivery=False,
			locale="Domestic",
			added_days=0,
		)
		doc_base.reload()

		# Create with added_days=5
		doc_shifted = _make_project(
			placement_agreement=placement,
			expedited_delivery=False,
			locale="Domestic",
			added_days=5,
		)
		doc_shifted.reload()

		# Compute expected shift: 5 business days
		expected_shift = add_business_days(placement, 5)
		shift_days = (getdate(expected_shift) - getdate(placement)).days

		# Verify each field is shifted by exactly shift_days
		base_provide = getdate(doc_base.provide_planogram_due)
		shifted_provide = getdate(doc_shifted.provide_planogram_due)
		self.assertEqual((shifted_provide - base_provide).days, shift_days)

		base_approve = getdate(doc_base.approve_planogram_and_locker_config_due)
		shifted_approve = getdate(doc_shifted.approve_planogram_and_locker_config_due)
		self.assertEqual((shifted_approve - base_approve).days, shift_days)

		base_sample = getdate(doc_base.sample_products_due)
		shifted_sample = getdate(doc_shifted.sample_products_due)
		self.assertEqual((shifted_sample - base_sample).days, shift_days)

	def test_one_field_failure_does_not_block_others(self):
		"""When one field's calculation fails, others still compute correctly."""
		placement = "2024-01-08"  # Monday
		real_add_business_days = add_business_days
		call_count = {"n": 0}

		def flaky(date, business_days):
			call_count["n"] += 1
			# Fail on the 3rd call (pog_created_in_database_due)
			if call_count["n"] == 3:
				raise ValueError("Simulated failure")
			return real_add_business_days(date, business_days)

		doc = _make_project(
			placement_agreement=placement,
			expedited_delivery=False,
			locale="Domestic",
			added_days=0,
		)

		with patch("ivm.deployments.event_handlers.project.add_business_days", side_effect=flaky):
			with patch("frappe.log_error") as mock_log:
				doc.save(ignore_permissions=True)

		# Verify log_error was called exactly once
		mock_log.assert_called_once()
		self.assertEqual(mock_log.call_args.kwargs.get("title"), "Due-date calculation failed")

		# Reload to check final state
		doc.reload()

		# The 3rd field (pog_created_in_database_due) should be None
		self.assertIsNone(doc.pog_created_in_database_due)

		# But other fields should have computed values
		self.assertIsNotNone(doc.provide_planogram_due)
		self.assertIsNotNone(doc.approve_planogram_and_locker_config_due)
		self.assertIsNotNone(doc.sample_products_due)
		self.assertIsNotNone(doc.sample_badge_due)


class TestBeforeValidate(ERPNextTestSuite):
	"""Test before_validate snapshots the current status."""

	def test_before_validate_snapshots_status(self):
		"""before_validate sets _original_status to current status."""
		doc = _make_project(status="Open")

		# Manually call before_validate to verify it sets _original_status
		from ivm.deployments.event_handlers.project import before_validate

		before_validate(doc)

		self.assertEqual(doc._original_status, "Open")

	def test_before_validate_snapshots_custom_status(self):
		"""before_validate snapshots custom statuses like 'In Progress'."""
		doc = _make_project(status="In Progress")

		from ivm.deployments.event_handlers.project import before_validate

		before_validate(doc)

		self.assertEqual(doc._original_status, "In Progress")


class TestValidateStatusRestore(ERPNextTestSuite):
	"""Test validate restores custom statuses that ERPNext core would reset."""

	def test_custom_status_delivered_is_restored(self):
		"""Custom status 'Delivered' is restored after save."""
		doc = _make_project(status="Open")
		doc.save(ignore_permissions=True)

		# Manually set to custom status and save
		doc.status = "Delivered"
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, "Delivered")

	def test_custom_status_in_progress_is_restored(self):
		"""Custom status 'In Progress' is restored after save."""
		doc = _make_project(status="Open")
		doc.save(ignore_permissions=True)

		doc.status = "In Progress"
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, "In Progress")

	def test_custom_status_on_hold_is_restored(self):
		"""Custom status 'On Hold' is restored after save."""
		doc = _make_project(status="Open")
		doc.save(ignore_permissions=True)

		doc.status = "On Hold"
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, "On Hold")

	def test_core_status_open_stays_open(self):
		"""Core status 'Open' is not affected by restore logic."""
		doc = _make_project(status="Open")
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, "Open")

	def test_core_status_completed_stays_completed(self):
		"""Core status 'Completed' is not affected by restore logic."""
		doc = _make_project(status="Completed")
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, "Completed")

	def test_core_status_cancelled_stays_cancelled(self):
		"""Core status 'Cancelled' is not affected by restore logic."""
		doc = _make_project(status="Cancelled")
		doc.save(ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.status, "Cancelled")


class TestLinkCrmDeal(ERPNextTestSuite):
	"""Test _link_crm_deal links Project to CRM Deal by custom_hubspot_deal_id."""

	def test_no_hubspot_deal_id_does_not_link(self):
		"""When custom_hubspot_deal_id is empty, custom_crm_deal stays unset."""
		doc = _make_project(custom_hubspot_deal_id=None, custom_crm_deal=None)
		doc.reload()

		self.assertIsNone(doc.custom_crm_deal)

	def test_already_linked_deal_not_overwritten(self):
		"""When custom_crm_deal is already set, it is not overwritten."""
		# Create two deals with different hubspot IDs
		deal1 = _make_deal(custom_hubspot_deal_id="hubspot_deal_1")
		_make_deal(custom_hubspot_deal_id="hubspot_deal_2")

		# Create project linked to deal1, but with deal2's hubspot ID
		# (simulating a mismatch that should NOT be auto-corrected)
		doc = _make_project(
			custom_hubspot_deal_id="hubspot_deal_2",
			custom_crm_deal=deal1.name,
		)
		doc.reload()

		# Should still be linked to deal1, not overwritten to deal2
		self.assertEqual(doc.custom_crm_deal, deal1.name)

	def test_hubspot_deal_id_links_to_matching_deal(self):
		"""When custom_hubspot_deal_id matches a CRM Deal, custom_crm_deal is set."""
		deal = _make_deal(custom_hubspot_deal_id="hubspot_test_123")

		doc = _make_project(
			custom_hubspot_deal_id="hubspot_test_123",
			custom_crm_deal=None,
		)
		doc.reload()

		self.assertEqual(doc.custom_crm_deal, deal.name)

	def test_no_matching_deal_leaves_crm_deal_empty(self):
		"""When custom_hubspot_deal_id has no matching CRM Deal, custom_crm_deal stays empty."""
		doc = _make_project(
			custom_hubspot_deal_id="hubspot_nonexistent",
			custom_crm_deal=None,
		)
		doc.reload()

		self.assertIsNone(doc.custom_crm_deal)


class TestAfterInsert(ERPNextTestSuite):
	"""Test after_insert calls create_machines_from_project."""

	def test_after_insert_calls_create_machines(self):
		"""after_insert calls create_machines_from_project with the doc."""
		from ivm.deployments.event_handlers.project import after_insert

		with patch(
			"ivm.deployments.services.create_machines_from_project.create_machines_from_project"
		) as mock_create:
			# Create project (hook is commented out, so we call after_insert directly)
			doc = _make_project()

			# Call after_insert directly
			after_insert(doc)

			# Mock should have been called exactly once
			mock_create.assert_called_once()

			# Verify the doc passed to the mock matches
			call_args = mock_create.call_args
			called_doc = call_args.args[0]
			self.assertEqual(called_doc.name, doc.name)
