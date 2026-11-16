"""Tests for ivm.integrations.hubspot.customer_resolution"""

import random
from unittest.mock import MagicMock, patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.integrations.hubspot import customer_resolution
from ivm.integrations.hubspot.customer_resolution import (
	apply_deal_customer,
	load_hubspot_companies,
	on_deal_customer_set,
	on_org_customer_set,
	resolve_deal_customer,
	set_value_tracked,
	validate_org,
)

_ICORP_POST = "ivm.integrations.icorp.provisioning.icorp_api_post"
_ICORP_GET = "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get"
_PRIMARY_CONTACT = "ivm.deployments.services.provision_client_from_deal.get_primary_contact"
_LINK_CONTACT = "ivm.deployments.services.provision_client_from_deal._link_contact_to_customer"
_APPLY_HOOK = "ivm.integrations.hubspot.customer_resolution.apply_deal_customer"
_DEAL_LEVEL = "Deal-level only"


def _ensure_deal_status(status):
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _uid():
	return frappe.generate_hash(length=8)


def _make_customer(name_hint="Cust", disabled=0):
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"{name_hint} {_uid()}",
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
			"disabled": disabled,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_org(name_hint="Org", website=None, customer=None, mode=None):
	# A Deal-level only organization may not carry a Client (validate_org refuses it), so a
	# Deal-level fixture is inserted blank and then given its state directly.
	doc = frappe.get_doc(
		{
			"doctype": "CRM Organization",
			"organization_name": f"{name_hint} {_uid()}",
			"website": website,
			"custom_customer": None if mode == _DEAL_LEVEL else customer,
			"custom_resolution_mode": None if mode == _DEAL_LEVEL else mode,
			"custom_hubspot_company_id": f"hs-{_uid()}",
		}
	)
	doc.insert(ignore_permissions=True)
	if mode == _DEAL_LEVEL:
		frappe.db.set_value(
			"CRM Organization",
			doc.name,
			{"custom_resolution_mode": _DEAL_LEVEL, "custom_customer": customer},
		)
		doc.reload()
	return doc


def _make_deal(organization=None, customer=None, deal_type="Existing Business", status="Qualification"):
	# Insert as Qualification: inserting as Won trips deal.on_update's Deployment Location
	# check. Move to the target status with set_value, which bypasses hooks.
	_ensure_deal_status(status)
	_ensure_deal_status("Qualification")
	deal = frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"organization": organization,
			"custom_customer": customer,
			"custom_deal_type": deal_type,
			"custom_hubspot_deal_name": f"Deal {_uid()}",
		}
	).insert(ignore_permissions=True)
	if status != "Qualification":
		frappe.db.set_value("CRM Deal", deal.name, "status", status)
		deal.reload()
	return deal


class TestResolveDealCustomer(ERPNextTestSuite):
	def test_deal_customer_used_when_org_blank(self):
		customer = _make_customer("DealOnly")
		org = _make_org("NoCustOrg")
		deal = _make_deal(organization=org.name, customer=customer.name)
		self.assertEqual(resolve_deal_customer(deal), customer.name)

	def test_org_customer_used_when_deal_blank(self):
		customer = _make_customer("OrgOnly")
		org = _make_org("OrgCust", customer=customer.name)
		deal = _make_deal(organization=org.name)
		self.assertEqual(resolve_deal_customer(deal), customer.name)

	def test_disabled_deal_customer_skipped(self):
		disabled = _make_customer("DisabledDeal", disabled=1)
		enabled = _make_customer("EnabledOrg")
		org = _make_org("SkipDisabledDeal", customer=enabled.name)
		deal = _make_deal(organization=org.name, customer=disabled.name)
		self.assertEqual(resolve_deal_customer(deal), enabled.name)

	def test_disabled_org_customer_skipped(self):
		disabled = _make_customer("DisabledOrg", disabled=1)
		org = _make_org("SkipDisabledOrg", customer=disabled.name)
		deal = _make_deal(organization=org.name)
		self.assertIsNone(resolve_deal_customer(deal))

	def test_conflict_logs_warning_and_deal_wins(self):
		deal_customer = _make_customer("ConflictDeal")
		org_customer = _make_customer("ConflictOrg")
		org = _make_org("Conflict", customer=org_customer.name)
		deal = _make_deal(organization=org.name, customer=deal_customer.name)

		logger = MagicMock()
		with patch("frappe.logger", return_value=logger):
			result = resolve_deal_customer(deal)

		self.assertEqual(result, deal_customer.name)
		logger.warning.assert_called_once()

	def test_neither_set_returns_none(self):
		org = _make_org("Neither")
		deal = _make_deal(organization=org.name)
		self.assertIsNone(resolve_deal_customer(deal))

	def test_deal_level_only_org_customer_ignored(self):
		customer = _make_customer("DLOIgnored")
		org = _make_org("DLOIgnoredOrg", customer=customer.name, mode=_DEAL_LEVEL)
		deal = _make_deal(organization=org.name)
		self.assertIsNone(resolve_deal_customer(deal))

	def test_deal_level_only_org_still_honours_deal_customer(self):
		org_customer = _make_customer("DLOOrgCust")
		deal_customer = _make_customer("DLODealCust")
		org = _make_org("DLODealOrg", customer=org_customer.name, mode=_DEAL_LEVEL)
		deal = _make_deal(organization=org.name, customer=deal_customer.name)
		self.assertEqual(resolve_deal_customer(deal), deal_customer.name)


def _make_location(crm_deal):
	return frappe.get_doc(
		{
			"doctype": "Deployment Location",
			"location_name": f"Loc {_uid()}",
			"crm_deal": crm_deal,
		}
	).insert(ignore_permissions=True)


def _make_icorp_client(customer_name):
	"""Single active own iCorp Client Link for a Customer. Name == icorp_client_id."""
	client_id = str(random.randint(5_000_000, 5_999_999))
	frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": client_id,
			"client_name": f"Client {client_id}",
			"customer": customer_name,
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
	return client_id


def _start_icorp_mocks():
	"""Mock every iCorp entry point used by the Customer/deal code paths. Returns (post, get)."""
	return patch(_ICORP_POST).start(), patch(_ICORP_GET).start()


class TestWonUnresolvedCustomer(ERPNextTestSuite):
	"""Won deal with no resolvable Customer: Projects are created blank, and no Tasks are made."""

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

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def _won_unresolved_deal(self, org=None, deal_type="Existing Business", locations=2):
		_ensure_deal_status("Won")
		deal = _make_deal(organization=org.name if org else None, deal_type=deal_type)
		for _ in range(locations):
			_make_location(deal.name)
		deal.status = "Won"
		deal.save(ignore_permissions=True)
		return frappe.get_doc("CRM Deal", deal.name)

	def test_won_unresolved_creates_blank_projects_and_no_tasks(self):
		org = _make_org("NoTaskOrg")
		tasks_before = frappe.db.count("Task")
		deal = self._won_unresolved_deal(org)

		projects = frappe.get_all("Project", filters={"custom_crm_deal": deal.name}, pluck="name")
		self.assertEqual(len(projects), 2)
		for name in projects:
			self.assertFalse(frappe.db.get_value("Project", name, "customer"))
		self.assertEqual(frappe.db.count("Task"), tasks_before)
		self.assertEqual(
			frappe.db.count("ToDo", {"reference_type": "CRM Deal", "reference_name": deal.name}), 0
		)

	def test_setting_customer_on_one_project_propagates(self):
		customer = _make_customer("TaskSibling")
		client_id = _make_icorp_client(customer.name)
		org = _make_org("TaskSiblingOrg")
		deal = self._won_unresolved_deal(org)

		first, second = sorted(
			frappe.get_all("Project", filters={"custom_crm_deal": deal.name}, pluck="name")
		)

		project = frappe.get_doc("Project", first)
		project.customer = customer.name
		project.icorp_client_id = client_id
		project.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		self.assertEqual(frappe.db.get_value("Project", second, "customer"), customer.name)
		self.assertEqual(frappe.db.get_value("Project", second, "icorp_client_id"), client_id)

		org_row = frappe.db.get_value(
			"CRM Organization",
			org.name,
			["custom_customer", "custom_customer_assignment_source"],
			as_dict=True,
		)
		self.assertEqual(org_row.custom_customer, customer.name)
		self.assertEqual(org_row.custom_customer_assignment_source, "Deal")

	def test_setting_client_on_won_deal_propagates_to_projects(self):
		customer = _make_customer("TaskDealSet")
		org = _make_org("TaskDealSetOrg")
		deal = self._won_unresolved_deal(org)

		deal.custom_customer = customer.name
		deal.save(ignore_permissions=True)

		for name in frappe.get_all("Project", filters={"custom_crm_deal": deal.name}, pluck="name"):
			self.assertEqual(frappe.db.get_value("Project", name, "customer"), customer.name)
		org_row = frappe.db.get_value(
			"CRM Organization",
			org.name,
			["custom_customer", "custom_customer_assignment_source"],
			as_dict=True,
		)
		self.assertEqual(org_row.custom_customer, customer.name)
		self.assertEqual(org_row.custom_customer_assignment_source, "Deal")

	def test_deal_level_only_org_resolve_leaves_org_blank(self):
		org = _make_org("TaskDLO", mode=_DEAL_LEVEL)
		deal = self._won_unresolved_deal(org)

		customer = _make_customer("TaskDLOCust")
		apply_deal_customer(deal.name, customer.name)

		org_row = frappe.db.get_value(
			"CRM Organization", org.name, ["custom_customer", "custom_resolution_mode"], as_dict=True
		)
		self.assertFalse(org_row.custom_customer)
		self.assertEqual(org_row.custom_resolution_mode, _DEAL_LEVEL)

	def test_project_insert_with_customer_does_not_propagate(self):
		customer = _make_customer("TaskInsertNoProp")
		deal = _make_deal()
		with patch("ivm.integrations.hubspot.customer_resolution.apply_deal_customer") as mock_apply:
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"Proj {_uid()}",
					"custom_crm_deal": deal.name,
					"customer": customer.name,
				}
			).insert(ignore_permissions=True, ignore_mandatory=True)
		mock_apply.assert_not_called()


class TestSetValueTracked(ERPNextTestSuite):
	"""set_value_tracked: write without hooks, record a Version only for real changes on tracked doctypes"""

	def _versions(self, deal_name):
		return frappe.get_all(
			"Version",
			filters={"ref_doctype": "CRM Deal", "docname": deal_name},
			fields=["name", "data"],
		)

	def test_tracked_write_creates_version_with_diff(self):
		customer = _make_customer("TrackedWrite")
		deal = _make_deal()

		set_value_tracked("CRM Deal", deal.name, {"custom_customer": customer.name})

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		versions = self._versions(deal.name)
		self.assertEqual(len(versions), 1)
		data = frappe.parse_json(versions[0].data)
		self.assertEqual(data["changed"], [["custom_customer", None, customer.name]])
		self.assertEqual(data["added"], [])
		self.assertEqual(data["removed"], [])

	def test_unchanged_write_is_noop(self):
		customer = _make_customer("TrackedSame")
		deal = _make_deal(customer=customer.name)
		before = frappe.db.get_value("CRM Deal", deal.name, "modified")

		set_value_tracked("CRM Deal", deal.name, {"custom_customer": customer.name})

		self.assertEqual(self._versions(deal.name), [])
		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "modified"), before)

	def test_blank_and_none_are_treated_as_same(self):
		deal = _make_deal()
		set_value_tracked("CRM Deal", deal.name, {"custom_customer": ""})
		self.assertEqual(self._versions(deal.name), [])

	def test_project_write_records_version_when_meta_tracks_changes(self):
		"""Project is track_changes-enabled via Property Setter on this site, so its write is versioned too"""
		deal = _make_deal()
		project = _make_deployment_for_deal(deal.name)
		self.addCleanup(lambda: frappe.delete_doc("Project", project.name, force=True))
		customer = _make_customer("TrackedProject")

		set_value_tracked("Project", project.name, {"customer": customer.name})

		self.assertEqual(frappe.db.get_value("Project", project.name, "customer"), customer.name)
		versions = frappe.get_all(
			"Version", filters={"ref_doctype": "Project", "docname": project.name}, pluck="data"
		)
		self.assertEqual(len(versions), 1)
		self.assertEqual(frappe.parse_json(versions[0])["changed"], [["customer", None, customer.name]])


class TestProjectCustomerVsDealClient(ERPNextTestSuite):
	"""A Deployment Project's Customer is compared with its deal's Client; the deal is never overwritten."""

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def _project(self, deal_name):
		project = _make_deployment_for_deal(deal_name)
		self.addCleanup(lambda: frappe.delete_doc("Project", project.name, force=True))
		return project

	def _set_project_customer(self, project_name, customer_name):
		project = frappe.get_doc("Project", project_name)
		project.customer = customer_name
		project.flags.ignore_mandatory = True
		project.save(ignore_permissions=True)

	def _comments_of_type(self, doctype, name):
		return frappe.get_all(
			"Comment",
			filters={"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"},
			pluck="content",
		)

	def test_blank_deal_client_is_filled_from_project_customer(self):
		customer = _make_customer("PCFill")
		org = _make_org("PCFillOrg")
		deal = _make_deal(organization=org.name)
		project = self._project(deal.name)

		self._set_project_customer(project.name, customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		self.assertEqual(self._comments_of_type("CRM Organization", org.name), [])

	def test_same_customer_as_deal_client_is_noop(self):
		customer = _make_customer("PCSame")
		org = _make_org("PCSameOrg")
		deal = _make_deal(organization=org.name, customer=customer.name)
		project = self._project(deal.name)

		self._set_project_customer(project.name, customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		self.assertEqual(self._comments_of_type("CRM Organization", org.name), [])
		self.assertEqual(self._comments_of_type("CRM Deal", deal.name), [])

	def test_different_customer_comments_on_deal_and_leaves_org_deal_and_siblings(self):
		deal_client = _make_customer("PCDealClient")
		project_customer = _make_customer("PCProjCustomer")
		org = _make_org("PCConflictOrg")
		deal = _make_deal(organization=org.name, customer=deal_client.name)
		project = self._project(deal.name)
		sibling = self._project(deal.name)
		org_before = frappe.db.get_value(
			"CRM Organization", org.name, ["custom_customer", "modified"], as_dict=True
		)

		self._set_project_customer(project.name, project_customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), deal_client.name)
		self.assertFalse(frappe.db.get_value("Project", sibling.name, "customer"))
		org_after = frappe.db.get_value(
			"CRM Organization", org.name, ["custom_customer", "modified"], as_dict=True
		)
		self.assertEqual(org_after.custom_customer, org_before.custom_customer)
		self.assertEqual(org_after.modified, org_before.modified)

		self.assertEqual(self._comments_of_type("CRM Organization", org.name), [])
		comments = self._comments_of_type("CRM Deal", deal.name)
		self.assertEqual(len(comments), 1)
		# Stored content gets rel="noopener noreferrer" added by sanitize, so match on link labels.
		self.assertIn("Deployment <a ", comments[0])
		self.assertIn(f">{project.name}</a> was given Customer ", comments[0])
		self.assertIn(f">{project_customer.name}</a>, but this deal's Client is ", comments[0])
		self.assertIn(f">{deal_client.name}</a>. Neither was changed.", comments[0])
		self.assertIn(project_customer.name, comments[0])

	def test_mismatch_comment_is_on_deal_without_organization(self):
		deal_client = _make_customer("PCNoOrgClient")
		project_customer = _make_customer("PCNoOrgProj")
		deal = _make_deal(customer=deal_client.name)
		project = self._project(deal.name)

		self._set_project_customer(project.name, project_customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), deal_client.name)
		comments = self._comments_of_type("CRM Deal", deal.name)
		self.assertEqual(len(comments), 1)
		self.assertIn("Neither was changed.", comments[0])
		self.assertIn(project.name, comments[0])

	def test_mismatch_comment_visible_in_deal_activities(self):
		from crm.api.activities import get_deal_activities

		deal_client = _make_customer("PCActDealClient")
		project_customer = _make_customer("PCActProjCustomer")
		deal = _make_deal(customer=deal_client.name)
		project = self._project(deal.name)

		self._set_project_customer(project.name, project_customer.name)

		activities = get_deal_activities(deal.name)[0]  # (activities, calls, notes, tasks, attachments)
		comment_activities = [a for a in activities if a.get("activity_type") == "comment"]
		self.assertTrue(
			any(
				project.name in (a.get("content") or "") and "Neither was changed." in a["content"]
				for a in comment_activities
			)
		)

	def test_apply_deal_customer_never_overwrites_set_client(self):
		existing = _make_customer("PCKeepExisting")
		other = _make_customer("PCTryOverwrite")
		deal = _make_deal(customer=existing.name)
		project = self._project(deal.name)

		apply_deal_customer(deal.name, other.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), existing.name)
		self.assertFalse(frappe.db.get_value("Project", project.name, "customer"))


class TestDealLeavesWon(ERPNextTestSuite):
	"""Won -> other status: one Comment listing the deal's Projects; Projects untouched."""

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

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def _won_deal_with_two_projects(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)
		_make_location(deal.name)
		deal.status = "Won"
		deal.save(ignore_permissions=True)
		return frappe.get_doc("CRM Deal", deal.name)

	def _comments_of_type(self, deal_name):
		return frappe.get_all(
			"Comment",
			filters={"reference_doctype": "CRM Deal", "reference_name": deal_name, "comment_type": "Comment"},
			pluck="content",
		)

	def test_leaving_won_adds_one_comment_listing_projects(self):
		deal = self._won_deal_with_two_projects()
		projects = sorted(frappe.get_all("Project", filters={"custom_crm_deal": deal.name}, pluck="name"))
		self.assertEqual(len(projects), 2)

		deal.status = "Discovery"
		deal.save(ignore_permissions=True)

		comments = self._comments_of_type(deal.name)
		self.assertEqual(len(comments), 1)
		self.assertIn("Deal is no longer Won in HubSpot (now Discovery). Deployments ", comments[0])
		self.assertIn("already exist and were not changed.", comments[0])
		self.assertNotIn(" on 20", comments[0])
		for name in projects:
			self.assertIn(name, comments[0])
			self.assertIn(f">{name}</a>", comments[0])
			self.assertEqual(frappe.db.get_value("Project", name, "customer"), None)

	def test_leaving_won_with_one_project_uses_singular_wording(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)
		deal.status = "Won"
		deal.save(ignore_permissions=True)
		projects = frappe.get_all("Project", filters={"custom_crm_deal": deal.name}, pluck="name")
		self.assertEqual(len(projects), 1)

		deal.status = "Discovery"
		deal.save(ignore_permissions=True)

		comments = self._comments_of_type(deal.name)
		self.assertEqual(len(comments), 1)
		self.assertIn("Deal is no longer Won in HubSpot (now Discovery). Deployment ", comments[0])
		self.assertIn(f">{projects[0]}</a> already exists and was not changed.", comments[0])
		self.assertNotIn("Deployments ", comments[0])

	def test_leaving_won_with_no_projects_says_none_created(self):
		deal = _make_deal(status="Won")  # set via set_value: no Projects are created
		self.assertEqual(frappe.db.count("Project", {"custom_crm_deal": deal.name}), 0)

		deal.status = "Discovery"
		deal.save(ignore_permissions=True)

		comments = self._comments_of_type(deal.name)
		self.assertEqual(
			comments,
			["Deal is no longer Won in HubSpot (now Discovery). No deployments had been created from it."],
		)

	def test_left_won_comment_visible_in_deal_activities(self):
		from crm.api.activities import get_deal_activities

		deal = self._won_deal_with_two_projects()
		deal.status = "Discovery"
		deal.save(ignore_permissions=True)

		activities = get_deal_activities(deal.name)[0]  # (activities, calls, notes, tasks, attachments)
		comment_activities = [a for a in activities if a.get("activity_type") == "comment"]
		self.assertTrue(
			any(
				"no longer Won in HubSpot (now Discovery)" in (a.get("content") or "")
				for a in comment_activities
			)
		)

	def test_projects_unchanged_when_leaving_won(self):
		deal = self._won_deal_with_two_projects()
		before = frappe.get_all(
			"Project", filters={"custom_crm_deal": deal.name}, fields=["name", "customer", "stage"]
		)

		deal.status = "Discovery"
		deal.save(ignore_permissions=True)

		after = frappe.get_all(
			"Project", filters={"custom_crm_deal": deal.name}, fields=["name", "customer", "stage"]
		)
		self.assertEqual(sorted(before, key=lambda r: r.name), sorted(after, key=lambda r: r.name))

	def test_no_comment_when_status_changes_without_leaving_won(self):
		deal = _make_deal(deal_type="New Business")
		deal.status = "Discovery"
		deal.save(ignore_permissions=True)
		self.assertEqual(self._comments_of_type(deal.name), [])

	def test_second_transition_away_from_won_comments_again(self):
		deal = self._won_deal_with_two_projects()
		deal.status = "Discovery"
		deal.save(ignore_permissions=True)
		deal.status = "Won"
		deal.save(ignore_permissions=True)
		deal.status = "Discovery"
		deal.save(ignore_permissions=True)
		self.assertEqual(len(self._comments_of_type(deal.name)), 2)


class TestReWonGuardAndDisabledCustomer(ERPNextTestSuite):
	"""Re-Won never duplicates a Deployment; a disabled deal Client yields blank Projects."""

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

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def test_rewon_does_not_duplicate_location_without_hubspot_site_id(self):
		_ensure_deal_status("Won")
		deal = _make_deal(deal_type="New Business")
		_make_location(deal.name)  # no hubspot_site_id

		deal.status = "Won"
		deal.save(ignore_permissions=True)
		self.assertEqual(frappe.db.count("Project", {"custom_crm_deal": deal.name}), 1)

		deal.reload()
		deal.status = "Discovery"
		deal.save(ignore_permissions=True)
		deal.status = "Won"
		deal.save(ignore_permissions=True)

		self.assertEqual(frappe.db.count("Project", {"custom_crm_deal": deal.name}), 1)

	def test_disabled_deal_customer_yields_blank_projects(self):
		_ensure_deal_status("Won")
		disabled = _make_customer("PCDisabledDeal", disabled=1)
		deal = _make_deal(deal_type="New Business", customer=disabled.name)
		_make_location(deal.name)

		deal.status = "Won"
		deal.save(ignore_permissions=True)

		projects = frappe.get_all("Project", filters={"custom_crm_deal": deal.name}, pluck="name")
		self.assertEqual(len(projects), 1)
		self.assertFalse(frappe.db.get_value("Project", projects[0], "customer"))


class TestErrorGuards(ERPNextTestSuite):
	"""A failing unit of Customer resolution is rolled back, logged, and never blocks the user's save."""

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

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def _error_logs(self, title_fragment):
		return frappe.get_all("Error Log", filters={"method": ["like", f"%{title_fragment}%"]}, pluck="name")

	def test_apply_failure_does_not_block_won_save_and_leaves_no_partial_writes(self):
		_ensure_deal_status("Won")
		customer = _make_customer("GuardApply")
		org = _make_org("GuardApplyOrg", customer=customer.name)
		deal = _make_deal(organization=org.name, deal_type="New Business")
		_make_location(deal.name)

		with patch(
			"ivm.integrations.hubspot.customer_resolution._fill_deal_projects",
			side_effect=ValueError("forced failure"),
		):
			deal.status = "Won"
			deal.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "status"), "Won")
		self.assertFalse(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"))
		self.assertEqual(frappe.db.count("Version", {"ref_doctype": "CRM Deal", "docname": deal.name}), 0)
		self.assertTrue(self._error_logs("Customer propagation failed"))

	def test_org_cascade_one_failing_deal_does_not_stop_others(self):
		customer = _make_customer("GuardCascade")
		org = _make_org("GuardCascadeOrg")
		failing = _make_deal(organization=org.name, status="Won")
		healthy = _make_deal(organization=org.name, status="Won")
		real_fill = customer_resolution._fill_deal_projects

		def fill_except_failing(crm_deal_name, customer_name):
			if crm_deal_name == failing.name:
				raise ValueError("forced failure")
			return real_fill(crm_deal_name, customer_name)

		with patch(
			"ivm.integrations.hubspot.customer_resolution._fill_deal_projects",
			side_effect=fill_except_failing,
		):
			org.custom_customer = customer.name
			org.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", healthy.name, "custom_customer"), customer.name)
		self.assertFalse(frappe.db.get_value("CRM Deal", failing.name, "custom_customer"))
		self.assertTrue(self._error_logs("Organization Customer propagation failed"))

	def test_project_failure_does_not_block_project_save(self):
		deal = _make_deal()
		project = _make_deployment_for_deal(deal.name)
		self.addCleanup(lambda: frappe.delete_doc("Project", project.name, force=True))
		customer = _make_customer("GuardProject")

		with patch(
			"ivm.integrations.hubspot.customer_resolution._propagate_project_customer",
			side_effect=ValueError("forced failure"),
		):
			doc = frappe.get_doc("Project", project.name)
			doc.customer = customer.name
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("Project", project.name, "customer"), customer.name)
		self.assertTrue(self._error_logs("Customer change on Project"))


class TestDealLevelOnlyGuard(ERPNextTestSuite):
	"""Manual Customer on a Deal-level only organization is refused."""

	def test_manual_customer_on_deal_level_only_org_throws(self):
		customer = _make_customer("DLOManual")
		org = _make_org("DLOManualOrg", mode=_DEAL_LEVEL)
		org.custom_customer = customer.name
		with self.assertRaises(frappe.ValidationError) as ctx:
			org.save(ignore_permissions=True)
		self.assertIn("Deal-level only", str(ctx.exception))
		self.assertFalse(frappe.db.get_value("CRM Organization", org.name, "custom_customer"))

	def test_clearing_mode_then_setting_customer_is_allowed(self):
		customer = _make_customer("DLOClear")
		org = _make_org("DLOClearOrg", mode=_DEAL_LEVEL)
		org.custom_resolution_mode = None
		org.custom_customer = customer.name
		org.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("CRM Organization", org.name, "custom_customer"), customer.name)


class TestOnOrgCustomerSet(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def test_fills_blank_won_deal_customer(self):
		_ensure_deal_status("Won")
		customer = _make_customer("FillBlank")
		org = _make_org("FillBlankOrg")
		deal = _make_deal(organization=org.name, status="Won")

		org.custom_customer = customer.name
		org.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)

	def test_never_overwrites_existing_deal_customer(self):
		_ensure_deal_status("Won")
		existing = _make_customer("KeepExisting")
		new = _make_customer("NewCandidate")
		org = _make_org("KeepOrg")
		deal = _make_deal(organization=org.name, customer=existing.name, status="Won")

		org.custom_customer = new.name
		org.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), existing.name)

	def test_fills_blank_project_customer(self):
		_ensure_deal_status("Won")
		customer = _make_customer("ProjFill")
		org = _make_org("ProjFillOrg")
		deal = _make_deal(organization=org.name, status="Won")
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"Proj {_uid()}", "custom_crm_deal": deal.name}
		).insert(ignore_permissions=True, ignore_mandatory=True)
		self.addCleanup(lambda: frappe.delete_doc("Project", project.name, force=True))

		org.custom_customer = customer.name
		org.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("Project", project.name, "customer"), customer.name)

	def test_org_link_backfill_on_won_new_business_makes_no_icorp_call(self):
		_ensure_deal_status("Won")
		customer = _make_customer("WinNoIcorpLink")
		org = _make_org("WinNoIcorpLinkOrg")
		deal = _make_deal(organization=org.name, deal_type="New Business", status="Won")

		org.custom_customer = customer.name
		org.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		self.mock_icorp_post.assert_not_called()
		self.mock_icorp_get.assert_not_called()


class TestValidateOrg(ERPNextTestSuite):
	def test_sets_assignment_source_manual_on_customer_set(self):
		customer = _make_customer("ValidateSrc")
		org = _make_org("ValidateSrcOrg", customer=customer.name)
		self.assertEqual(
			frappe.db.get_value("CRM Organization", org.name, "custom_customer_assignment_source"),
			"Manual",
		)

	def test_validate_org_uses_flag_when_set(self):
		customer = _make_customer("ValidateFlag")
		org = frappe.get_doc("CRM Organization", _make_org("ValidateFlagOrg").name)
		org.custom_customer = customer.name
		org.flags.customer_assignment_source = "Provisioning"
		validate_org(org)
		self.assertEqual(org.custom_customer_assignment_source, "Provisioning")


class TestLoadHubspotCompanies(ERPNextTestSuite):
	def test_returns_linked_orgs_with_deal_counts(self):
		customer = _make_customer("OnloadCust")
		org = _make_org("OnloadOrg", customer=customer.name)
		_make_deal(organization=org.name)
		_make_deal(organization=org.name)

		doc = frappe.get_doc("Customer", customer.name)
		load_hubspot_companies(doc)

		companies = doc.get_onload("hubspot_companies")
		match = next(c for c in companies if c["name"] == org.name)
		self.assertEqual(match["deal_count"], 2)


def _make_project(deal_name, customer=None):
	project = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"Proj {_uid()}",
			"custom_crm_deal": deal_name,
			"customer": customer,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)
	return project


class TestApplyDealCustomer(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def test_sets_deal_customer(self):
		customer = _make_customer("ApplySets")
		deal = _make_deal()

		apply_deal_customer(deal.name, customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)

	def test_links_primary_contact_to_customer(self):
		customer = _make_customer("ApplyContact")
		deal = _make_deal()
		contact = MagicMock()
		with patch(_PRIMARY_CONTACT, return_value=contact) as mock_primary, patch(_LINK_CONTACT) as mock_link:
			apply_deal_customer(deal.name, customer.name)

		mock_primary.assert_called_once()
		mock_link.assert_called_once_with(contact, customer.name)

	def test_backfills_blank_project_but_never_overwrites(self):
		customer = _make_customer("ApplyProj")
		other = _make_customer("ApplyProjOther")
		deal = _make_deal()
		blank = _make_project(deal.name)
		set_already = _make_project(deal.name, customer=other.name)
		self.addCleanup(lambda: frappe.delete_doc("Project", blank.name, force=True))
		self.addCleanup(lambda: frappe.delete_doc("Project", set_already.name, force=True))

		apply_deal_customer(deal.name, customer.name)

		self.assertEqual(frappe.db.get_value("Project", blank.name, "customer"), customer.name)
		self.assertEqual(frappe.db.get_value("Project", set_already.name, "customer"), other.name)

	def test_new_business_makes_no_icorp_call(self):
		customer = _make_customer("ApplyNB")
		deal = _make_deal(deal_type="New Business")

		apply_deal_customer(deal.name, customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		self.mock_icorp_post.assert_not_called()
		self.mock_icorp_get.assert_not_called()

	def test_existing_business_makes_no_icorp_call(self):
		customer = _make_customer("ApplyEB")
		deal = _make_deal(deal_type="Existing Business")

		apply_deal_customer(deal.name, customer.name)

		self.mock_icorp_post.assert_not_called()
		self.mock_icorp_get.assert_not_called()


class TestAutoLearnOrgCustomer(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def test_blank_org_learns_customer_with_deal_source(self):
		customer = _make_customer("LearnBlank")
		org = _make_org("LearnBlankOrg")
		deal = _make_deal(organization=org.name, status="Won")

		apply_deal_customer(deal.name, customer.name)

		org_row = frappe.db.get_value(
			"CRM Organization",
			org.name,
			["custom_customer", "custom_customer_assignment_source"],
			as_dict=True,
		)
		self.assertEqual(org_row.custom_customer, customer.name)
		self.assertEqual(org_row.custom_customer_assignment_source, "Deal")

	def test_learn_backfills_other_blank_won_deals(self):
		customer = _make_customer("LearnBackfill")
		org = _make_org("LearnBackfillOrg")
		deal = _make_deal(organization=org.name, status="Won")
		other_deal = _make_deal(organization=org.name, status="Won")

		apply_deal_customer(deal.name, customer.name)

		self.assertEqual(frappe.db.get_value("CRM Deal", other_deal.name, "custom_customer"), customer.name)

	def test_same_customer_is_noop(self):
		customer = _make_customer("LearnSame")
		org = _make_org("LearnSameOrg", customer=customer.name)
		deal = _make_deal(organization=org.name, status="Won")

		apply_deal_customer(deal.name, customer.name)

		org_row = frappe.db.get_value(
			"CRM Organization",
			org.name,
			["custom_customer", "custom_resolution_mode", "custom_customer_assignment_source"],
			as_dict=True,
		)
		self.assertEqual(org_row.custom_customer, customer.name)
		self.assertFalse(org_row.custom_resolution_mode)
		self.assertEqual(org_row.custom_customer_assignment_source, "Manual")

	def test_different_customer_marks_org_deal_level_only(self):
		org_customer = _make_customer("ConflictOrgCust")
		deal_customer = _make_customer("ConflictDealCust")
		org = _make_org("ConflictOrg", customer=org_customer.name)
		deal = _make_deal(organization=org.name, customer=deal_customer.name, status="Won")

		apply_deal_customer(deal.name, deal_customer.name)

		org_row = frappe.db.get_value(
			"CRM Organization",
			org.name,
			["custom_customer", "custom_resolution_mode", "custom_customer_assignment_source"],
			as_dict=True,
		)
		self.assertFalse(org_row.custom_customer)
		self.assertEqual(org_row.custom_resolution_mode, _DEAL_LEVEL)
		self.assertFalse(org_row.custom_customer_assignment_source)
		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), deal_customer.name)

		org_comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "CRM Organization",
				"reference_name": org.name,
				"comment_type": "Comment",
			},
			pluck="content",
		)
		self.assertEqual(org_comments, [])

		deal_comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": "CRM Deal", "reference_name": deal.name, "comment_type": "Comment"},
			pluck="content",
		)
		self.assertEqual(len(deal_comments), 1)
		content = deal_comments[0]
		self.assertIn("Customer conflict: this deal resolved to", content)
		self.assertIn(f">{deal_customer.name}</a>", content)
		self.assertIn(f">{org.name}</a>", content)
		self.assertIn("was already linked to", content)
		self.assertIn(f">{org_customer.name}</a>", content)
		self.assertIn(f"set to {_DEAL_LEVEL}", content)
		self.assertIn("No action needed unless this looks wrong.", content)

	def test_second_conflict_keeps_org_deal_level_only_and_adds_no_todo(self):
		org_customer = _make_customer("DupOrgCust")
		first = _make_customer("DupFirst")
		second = _make_customer("DupSecond")
		org = _make_org("DupOrg", customer=org_customer.name)
		deal_one = _make_deal(organization=org.name, status="Won")
		deal_two = _make_deal(organization=org.name, status="Won")

		apply_deal_customer(deal_one.name, first.name)
		apply_deal_customer(deal_two.name, second.name)

		self.assertEqual(
			frappe.db.count("ToDo", {"reference_type": "CRM Organization", "reference_name": org.name}), 0
		)
		self.assertEqual(
			frappe.db.get_value("CRM Organization", org.name, "custom_resolution_mode"), _DEAL_LEVEL
		)


class TestOnDealCustomerSet(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.mock_apply = patch(_APPLY_HOOK).start()
		self.addCleanup(patch.stopall)

	def test_fires_when_client_set_on_already_won_deal(self):
		customer = _make_customer("HookFires")
		deal = _make_deal(status="Won")

		deal.custom_customer = customer.name
		deal.save(ignore_permissions=True)

		self.mock_apply.assert_called_once_with(deal.name, customer.name)

	def test_does_not_fire_when_status_not_won(self):
		customer = _make_customer("HookNotWon")
		deal = _make_deal(status="Qualification")

		deal.custom_customer = customer.name
		deal.save(ignore_permissions=True)

		self.mock_apply.assert_not_called()

	def test_does_not_fire_on_won_transition_save(self):
		customer = _make_customer("HookTransition")
		deal = _make_deal(status="Qualification")
		frappe.get_doc(
			{
				"doctype": "Deployment Location",
				"location_name": f"Loc {_uid()}",
				"crm_deal": deal.name,
			}
		).insert(ignore_permissions=True)

		with (
			patch("ivm.deployments.event_handlers.deal.apply_deal_customer") as mock_deal_apply,
			patch("ivm.deployments.event_handlers.deal.create_projects_from_deal", return_value=[]),
		):
			deal.status = "Won"
			deal.custom_customer = customer.name
			deal.save(ignore_permissions=True)

		mock_deal_apply.assert_called_once_with(deal.name, customer.name)
		self.mock_apply.assert_not_called()

	def test_does_not_fire_when_changing_existing_customer(self):
		first = _make_customer("HookFirst")
		second = _make_customer("HookSecond")
		deal = _make_deal(customer=first.name, status="Won")

		deal.custom_customer = second.name
		deal.save(ignore_permissions=True)

		self.mock_apply.assert_not_called()


def _make_deployment_for_deal(deal_name, customer=None, icorp_client_id=None):
	"""Deployment Project as create_projects_from_deal would insert it (system insert)."""
	return frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"Dep {_uid()}",
			"project_type": "Deployment",
			"custom_crm_deal": deal_name,
			"customer": customer,
			"icorp_client_id": icorp_client_id,
		}
	).insert(ignore_permissions=True, ignore_mandatory=True)


class TestWinMakesNoIcorpCall(ERPNextTestSuite):
	"""Won New Business resolution must never touch iCorp; the Customer form does that on request."""

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def test_won_new_business_with_resolvable_customer_makes_no_icorp_call(self):
		_ensure_deal_status("Won")
		customer = _make_customer("WinNoIcorp")
		org = _make_org("WinNoIcorpOrg", customer=customer.name)
		deal = _make_deal(organization=org.name, deal_type="New Business")
		_make_location(deal.name)

		deal.status = "Won"
		deal.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "custom_customer"), customer.name)
		self.assertTrue(frappe.db.exists("Project", {"custom_crm_deal": deal.name}))
		self.mock_icorp_post.assert_not_called()
		self.mock_icorp_get.assert_not_called()


class TestFillDealProjects(ERPNextTestSuite):
	"""_fill_deal_projects: fill blanks on Projects of the deal, never overwrite."""

	def setUp(self):
		super().setUp()
		self.mock_icorp_post, self.mock_icorp_get = _start_icorp_mocks()
		self.addCleanup(patch.stopall)

	def test_sets_client_on_project_that_has_customer_but_no_client(self):
		customer = _make_customer("FillClient")
		client_id = _make_icorp_client(customer.name)
		deal = _make_deal(deal_type="Existing Business")
		project = _make_deployment_for_deal(deal.name, customer=customer.name)

		apply_deal_customer(deal.name, customer.name)

		row = frappe.db.get_value("Project", project.name, ["customer", "icorp_client_id"], as_dict=True)
		self.assertEqual(row.customer, customer.name)
		self.assertEqual(row.icorp_client_id, client_id)

	def test_does_not_overwrite_existing_client_on_project(self):
		customer = _make_customer("FillKeep")
		_make_icorp_client(customer.name)
		existing_client = _make_icorp_client(customer.name)
		deal = _make_deal(deal_type="Existing Business")
		project = _make_deployment_for_deal(
			deal.name, customer=customer.name, icorp_client_id=existing_client
		)

		apply_deal_customer(deal.name, customer.name)

		self.assertEqual(frappe.db.get_value("Project", project.name, "icorp_client_id"), existing_client)

	def test_leaves_project_on_different_customer_alone(self):
		customer = _make_customer("FillMine")
		other = _make_customer("FillOther")
		_make_icorp_client(customer.name)
		deal = _make_deal(deal_type="Existing Business")
		project = _make_deployment_for_deal(deal.name, customer=other.name)

		apply_deal_customer(deal.name, customer.name)

		row = frappe.db.get_value("Project", project.name, ["customer", "icorp_client_id"], as_dict=True)
		self.assertEqual(row.customer, other.name)
		self.assertFalse(row.icorp_client_id)

	def test_no_client_filled_when_customer_has_several_own_clients(self):
		customer = _make_customer("FillAmbiguous")
		_make_icorp_client(customer.name)
		_make_icorp_client(customer.name)
		deal = _make_deal(deal_type="Existing Business")
		project = _make_deployment_for_deal(deal.name, customer=customer.name)

		apply_deal_customer(deal.name, customer.name)

		self.assertFalse(frappe.db.get_value("Project", project.name, "icorp_client_id"))
