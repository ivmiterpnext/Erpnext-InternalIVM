"""Integration tests for ivm.deployments.event_handlers.project"""

import random
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
	"""Create and insert a Project with specified parameters.

	project_type is left unset, so it takes the site default ("Deployment"), which
	means the Deployment customer/iCorp rules apply: the Project gets a Customer
	with one iCorp client so it validates like a real deployment."""
	if not project_name:
		project_name = f"Test Project {frappe.generate_hash(length=8)}"

	customer, icorp_client_id = _make_customer_with_icorp_client()
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
			"customer": customer,
			"icorp_client_id": icorp_client_id,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_customer_with_icorp_client():
	"""A Customer with exactly one active own iCorp client, for Deployment Projects."""
	customer = _make_customer(frappe.generate_hash(length=6))
	client_id = str(random.randint(800_000_000, 899_999_999))
	frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": client_id,
			"client_name": f"Test Client {client_id}",
			"customer": customer,
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
	return customer, client_id


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


def _make_customer(name_suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": "_Test Customer Group",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Customer {name_suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def _make_icorp_client(icorp_client_id, customer=None, parent_client=None):
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": icorp_client_id,
			"client_name": f"Test Client {icorp_client_id}",
			"customer": customer,
			"parent_client": parent_client,
			"is_active": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_deployment_project(project_name=None, customer=None, icorp_client_id=None, stage=None):
	if not project_name:
		project_name = f"Test Deployment {frappe.generate_hash(length=8)}"
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"project_type": "Deployment",
			"customer": customer,
			"icorp_client_id": icorp_client_id,
			"stage": stage,
		}
	)
	return doc


class TestValidateIcorpClientId(ERPNextTestSuite):
	"""Test _validate_icorp_client_id, called from Project.validate()."""

	def setUp(self):
		super().setUp()
		self._cleanup = []
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

	def tearDown(self):
		for doctype, name in reversed(self._cleanup):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		super().tearDown()

	def _track(self, doctype, name):
		self._cleanup.append((doctype, name))
		return name

	def test_new_deployment_without_client_throws(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"NoClient {uid}"))

		doc = _make_deployment_project(customer=customer)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_no_clients_message_links_to_customer(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"NoClientMsg {uid}"))

		doc = _make_deployment_project(customer=customer)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)

		message = str(ctx.exception)
		self.assertIn(frappe.utils.get_link_to_form("Customer", customer), message)
		self.assertIn("has no iCorp client yet", message)
		self.assertIn("Add one on the", message)
		self.assertIn("Customer's iCorp tab</a>, then pick it here.", message)
		self.assertIn(
			frappe.utils.escape_html(frappe.utils.get_url_to_form("Customer", customer) + "#icorp_tab") + '"',
			message,
		)
		self.assertNotIn("Add iCorp client", message)
		self.assertNotIn("Select the iCorp Client for this deployment.", message)

	def test_inactive_only_customer_message_names_inactive_client(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"InactiveOnly {uid}"))
		client = self._track("iCorp Client Link", _make_icorp_client("100050", customer=customer))
		frappe.db.set_value("iCorp Client Link", client, "is_active", 0)

		doc = _make_deployment_project(customer=customer)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)

		message = str(ctx.exception)
		self.assertIn(frappe.utils.get_link_to_form("Customer", customer), message)
		self.assertIn("only has inactive iCorp clients (100050)", message)
		self.assertIn("or add one on the", message)
		self.assertIn("Customer's iCorp tab</a>, then pick it here.", message)
		self.assertIn(
			frappe.utils.escape_html(frappe.utils.get_url_to_form("Customer", customer) + "#icorp_tab") + '"',
			message,
		)
		self.assertNotIn("Create new in iCorp", message)
		self.assertNotIn("has no iCorp client yet", message)
		self.assertNotIn("Select the iCorp Client for this deployment.", message)

	def test_none_message_is_not_inactive_variant(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"NoneVariant {uid}"))

		doc = _make_deployment_project(customer=customer)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)

		message = str(ctx.exception)
		self.assertIn("has no iCorp client yet", message)
		self.assertNotIn("only has inactive", message)

	def test_customer_with_clients_but_none_selected_keeps_select_message(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"HasClients {uid}"))
		self._track("iCorp Client Link", _make_icorp_client("100040", customer=customer))

		doc = _make_deployment_project(customer=customer)
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)

		self.assertIn("Select the iCorp Client for this deployment.", str(ctx.exception))

	def test_deployment_without_customer_is_blocked(self):
		doc = _make_deployment_project()
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.insert(ignore_permissions=True)

		self.assertIn("Select the Customer for this deployment before saving.", str(ctx.exception))

	def test_system_insert_without_customer_is_allowed(self):
		"""create_projects_from_deal inserts with ignore_mandatory=True; that path must still work."""
		doc = _make_deployment_project()
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._track("Project", doc.name)

		self.assertFalse(doc.customer)
		self.assertTrue(frappe.db.exists("Project", doc.name))

	def test_legacy_project_without_client_saves_unchanged(self):
		"""A pre-existing Deployment Project with no icorp_client_id, saved without
		touching customer/icorp_client_id/stage, must NOT throw.

		Simulates a record that existed before this validation existed: insert with
		no customer (so validate()'s strict block never fires), then backdate the
		customer directly via frappe.db.set_value -- a raw DB write that bypasses
		validate() entirely, exactly like a record that predates this field."""
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"Legacy {uid}"))

		doc = _make_deployment_project()
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._track("Project", doc.name)

		frappe.db.set_value("Project", doc.name, "customer", customer)

		# Fresh object (no ignore_mandatory flag left over from insert), saved as a user would.
		doc = frappe.get_doc("Project", doc.name)
		doc.save(ignore_permissions=True)
		doc.reload()
		self.assertFalse(doc.icorp_client_id)
		self.assertEqual(doc.customer, customer)

	def test_managed_client_swaps_customer_and_sets_partner(self):
		uid = frappe.generate_hash(length=6)
		partner_customer = self._track("Customer", _make_customer(f"PartnerSwap {uid}"))
		end_customer = self._track("Customer", _make_customer(f"EndSwap {uid}"))
		parent = self._track("iCorp Client Link", _make_icorp_client("100001", customer=partner_customer))
		managed_client = self._track(
			"iCorp Client Link",
			_make_icorp_client("100002", customer=end_customer, parent_client=parent),
		)

		doc = _make_deployment_project(customer=partner_customer, icorp_client_id=managed_client)
		doc.insert(ignore_permissions=True)
		self._track("Project", doc.name)

		self.assertEqual(doc.customer, end_customer)
		self.assertEqual(doc.partner_customer, partner_customer)

	def test_row_client_from_different_customer_throws(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"RowCust {uid}"))
		other_customer = self._track("Customer", _make_customer(f"OtherCust {uid}"))
		own_client = self._track("iCorp Client Link", _make_icorp_client("100003", customer=customer))
		other_client = self._track("iCorp Client Link", _make_icorp_client("100004", customer=other_customer))

		doc = _make_deployment_project(customer=customer, icorp_client_id=own_client)
		doc.append(
			"custom_deployment_smartstation_details", {"machine_name": "M1", "icorp_client_id": other_client}
		)

		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_stage_leaving_waiting_assignment_without_client_throws(self):
		"""Simulates a legacy record (see test_legacy_project_without_client_saves_unchanged
		for why the fixture is built this way) sitting at stage='Waiting Assignment' with no
		client, that then gets moved forward -- this is the one case where a legacy record
		DOES get required to pick a client."""
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"StageCust {uid}"))

		doc = _make_deployment_project(stage="Waiting Assignment")
		doc.insert(ignore_permissions=True, ignore_mandatory=True)
		self._track("Project", doc.name)

		frappe.db.set_value("Project", doc.name, "customer", customer)

		# Fresh object: the insert above left flags.ignore_mandatory set on `doc`.
		doc = frappe.get_doc("Project", doc.name)
		self.assertFalse(doc.icorp_client_id)
		self.assertEqual(doc.stage, "Waiting Assignment")

		doc.stage = "Assigned"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_blank_rows_inherit_project_client(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"RowInherit {uid}"))
		c1 = self._track("iCorp Client Link", _make_icorp_client("100030", customer=customer))
		self._track("iCorp Client Link", _make_icorp_client("100031", customer=customer))

		doc = _make_deployment_project(customer=customer, icorp_client_id=c1)
		doc.append("custom_deployment_smartstation_details", {"machine_name": "INH-1"})
		doc.insert(ignore_permissions=True)
		self._track("Project", doc.name)

		self.assertEqual(doc.custom_deployment_smartstation_details[0].icorp_client_id, c1)

	def test_rows_follow_project_client_change_but_keep_manual_overrides(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"RowFollow {uid}"))
		c1 = self._track("iCorp Client Link", _make_icorp_client("100032", customer=customer))
		c2 = self._track("iCorp Client Link", _make_icorp_client("100033", customer=customer))
		c3 = self._track("iCorp Client Link", _make_icorp_client("100034", customer=customer))

		doc = _make_deployment_project(customer=customer, icorp_client_id=c1)
		doc.append("custom_deployment_smartstation_details", {"machine_name": "FOL-1"})
		doc.append("custom_deployment_smartlocker_details", {"machine_name": "FOL-2", "icorp_client_id": c2})
		doc.insert(ignore_permissions=True)
		self._track("Project", doc.name)

		doc.reload()
		doc.icorp_client_id = c3
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertEqual(doc.custom_deployment_smartstation_details[0].icorp_client_id, c3)
		self.assertEqual(doc.custom_deployment_smartlocker_details[0].icorp_client_id, c2)
