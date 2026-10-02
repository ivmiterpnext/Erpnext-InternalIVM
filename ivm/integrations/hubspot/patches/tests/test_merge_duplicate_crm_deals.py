"""Integration tests for ivm.integrations.hubspot.patches.merge_duplicate_crm_deals

These tests create multiple CRM Deal rows sharing one custom_hubspot_deal_id
on purpose — that's the exact pre-patch state this patch is meant to clean
up. Once `bench migrate` has run with the unique: 1 flag from
ivm/ivm/custom/crm_deal.json applied (which it has, on any site that has run
this patch's own migrate at least once — see merge_duplicate_crm_deals.py's
docstring on ordering), a real UNIQUE KEY sits on that column, and no insert
or update — ORM or raw SQL, there's no bypassing a storage-engine constraint
— can create a second row with the same value. setUpModule/tearDownModule
below drop that index before this module's tests run and restore it
afterward, so this file can still exercise the patch's duplicate-handling
logic even on a site where the constraint it depends on is already live.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.integrations.hubspot.patches.merge_duplicate_crm_deals import (
	_clear_empty_hubspot_ids,
	_dedupe_survivor_files,
	_find_duplicate_groups,
	_gather_facts,
	_linked_total,
	_merge_group,
	_pick_survivor,
	execute,
)

_INDEX_NAME = "custom_hubspot_deal_id"
_HAD_UNIQUE_INDEX = None


def setUpModule():
	"""Drop the unique index on CRM Deal.custom_hubspot_deal_id, if present,
	for the duration of this test module. No-op (records nothing to restore)
	on a site where the index hasn't been applied yet.
	"""
	global _HAD_UNIQUE_INDEX
	frappe.db.commit()  # avoid ImplicitCommitError on the DDL below
	existing = frappe.db.sql(
		"SHOW INDEX FROM `tabCRM Deal` WHERE Key_name = %s", (_INDEX_NAME,), as_dict=True
	)
	_HAD_UNIQUE_INDEX = bool(existing)
	if _HAD_UNIQUE_INDEX:
		frappe.db.sql_ddl(f"ALTER TABLE `tabCRM Deal` DROP INDEX `{_INDEX_NAME}`")


def tearDownModule():
	"""Restore the unique index if setUpModule found and dropped one."""
	if _HAD_UNIQUE_INDEX:
		frappe.db.commit()
		frappe.db.sql_ddl(f"ALTER TABLE `tabCRM Deal` ADD UNIQUE INDEX `{_INDEX_NAME}` (`{_INDEX_NAME}`)")


def _ensure_deal_status(status):
	"""Create CRM Deal Status if it doesn't exist."""
	if not frappe.db.exists("CRM Deal Status", status):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
			ignore_permissions=True,
		)


def _make_deal(hubspot_id=None, customer=None):
	"""Create a CRM Deal with optional custom_hubspot_deal_id and custom_customer."""
	_ensure_deal_status("Qualification")
	uid = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": "Qualification",
			"custom_hubspot_deal_name": f"Test Deal {uid}",
			"custom_customer": customer,
		}
	)
	doc.insert(ignore_permissions=True)
	if hubspot_id is not None:
		frappe.db.set_value("CRM Deal", doc.name, "custom_hubspot_deal_id", hubspot_id)
	return doc


def _ensure_company():
	"""Create test company if it doesn't exist."""
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


def _make_project(crm_deal):
	"""Create a Project linked to a CRM Deal."""
	_ensure_company()
	uid = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"Proj {uid}",
			"company": "IVM",
			"custom_crm_deal": crm_deal,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_location(crm_deal):
	"""Create a Deployment Location linked to a CRM Deal."""
	uid = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "Deployment Location",
			"location_name": f"Loc {uid}",
			"crm_deal": crm_deal,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_note(crm_deal):
	"""Create an FCRM Note linked to a CRM Deal."""
	uid = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "FCRM Note",
			"title": f"Note {uid}",
			"reference_doctype": "CRM Deal",
			"reference_docname": crm_deal,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_task(crm_deal):
	"""Create a CRM Task linked to a CRM Deal."""
	uid = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "CRM Task",
			"title": f"Task {uid}",
			"reference_doctype": "CRM Deal",
			"reference_docname": crm_deal,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_file(crm_deal, file_name):
	"""Create a File attached to a CRM Deal."""
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": "CRM Deal",
			"attached_to_name": crm_deal,
			"content": "test content",
			"is_private": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _make_customer(name_hint="Cust"):
	"""Create a Customer for linking to CRM Deal."""
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"{name_hint} {frappe.generate_hash(length=8)}",
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestClearEmptyHubspotIds(ERPNextTestSuite):
	"""Tests for _clear_empty_hubspot_ids helper"""

	def test_empty_hubspot_id_cleared_to_null(self):
		"""Empty string custom_hubspot_deal_id should be converted to NULL."""
		deal = _make_deal()
		# Force empty string (not None)
		frappe.db.set_value("CRM Deal", deal.name, "custom_hubspot_deal_id", "", update_modified=False)

		_clear_empty_hubspot_ids()

		# Should be NULL now
		value = frappe.db.get_value("CRM Deal", deal.name, "custom_hubspot_deal_id")
		self.assertIsNone(value)

	def test_noop_on_null_values(self):
		"""NULL values should remain NULL."""
		deal = _make_deal()
		# Ensure it's NULL
		frappe.db.set_value("CRM Deal", deal.name, "custom_hubspot_deal_id", None, update_modified=False)

		_clear_empty_hubspot_ids()

		# Should still be NULL
		value = frappe.db.get_value("CRM Deal", deal.name, "custom_hubspot_deal_id")
		self.assertIsNone(value)

	def test_noop_on_non_empty_values(self):
		"""Non-empty values should not be changed."""
		deal = _make_deal(hubspot_id="hs_123")

		_clear_empty_hubspot_ids()

		# Should still be hs_123
		value = frappe.db.get_value("CRM Deal", deal.name, "custom_hubspot_deal_id")
		self.assertEqual(value, "hs_123")


class TestFindDuplicateGroups(ERPNextTestSuite):
	"""Tests for _find_duplicate_groups helper"""

	def test_no_duplicates_returns_empty(self):
		"""Single deal with unique hubspot_id should not appear in results."""
		_make_deal(hubspot_id="hs_unique_123")

		groups = _find_duplicate_groups()

		self.assertEqual(groups, {})

	def test_finds_pair_of_duplicates(self):
		"""Two deals with same hubspot_id should be found."""
		deal1 = _make_deal(hubspot_id="hs_dup_001")
		deal2 = _make_deal(hubspot_id="hs_dup_001")

		groups = _find_duplicate_groups()

		self.assertIn("hs_dup_001", groups)
		self.assertEqual(set(groups["hs_dup_001"]), {deal1.name, deal2.name})

	def test_finds_triple_duplicates(self):
		"""Three deals with same hubspot_id should all be found."""
		deal1 = _make_deal(hubspot_id="hs_dup_002")
		deal2 = _make_deal(hubspot_id="hs_dup_002")
		deal3 = _make_deal(hubspot_id="hs_dup_002")

		groups = _find_duplicate_groups()

		self.assertIn("hs_dup_002", groups)
		self.assertEqual(set(groups["hs_dup_002"]), {deal1.name, deal2.name, deal3.name})

	def test_ignores_null_hubspot_ids(self):
		"""Deals with NULL hubspot_id should not be grouped."""
		_make_deal()  # No hubspot_id
		_make_deal()  # No hubspot_id

		groups = _find_duplicate_groups()

		self.assertEqual(groups, {})

	def test_orders_by_creation_oldest_first(self):
		"""Results should be ordered by creation time, oldest first."""
		deal1 = _make_deal(hubspot_id="hs_dup_003")
		deal2 = _make_deal(hubspot_id="hs_dup_003")
		deal3 = _make_deal(hubspot_id="hs_dup_003")

		# Force creation order: deal3 oldest, deal1 newest
		frappe.db.set_value(
			"CRM Deal",
			deal3.name,
			"creation",
			datetime.now() - timedelta(hours=2),
			update_modified=False,
		)
		frappe.db.set_value(
			"CRM Deal",
			deal2.name,
			"creation",
			datetime.now() - timedelta(hours=1),
			update_modified=False,
		)

		groups = _find_duplicate_groups()

		# Should be ordered: deal3 (oldest), deal2, deal1 (newest)
		self.assertEqual(groups["hs_dup_003"], [deal3.name, deal2.name, deal1.name])


class TestGatherFacts(ERPNextTestSuite):
	"""Tests for _gather_facts helper"""

	def test_counts_projects(self):
		"""Should count linked projects."""
		deal = _make_deal()
		_make_project(deal.name)
		_make_project(deal.name)

		facts = _gather_facts(deal.name)

		self.assertEqual(facts["project_count"], 2)

	def test_counts_locations(self):
		"""Should count linked deployment locations."""
		deal = _make_deal()
		_make_location(deal.name)
		_make_location(deal.name)

		facts = _gather_facts(deal.name)

		self.assertEqual(facts["location_count"], 2)

	def test_extracts_customer(self):
		"""Should extract custom_customer value."""
		customer = _make_customer()
		deal = _make_deal(customer=customer.name)

		facts = _gather_facts(deal.name)

		self.assertEqual(facts["custom_customer"], customer.name)

	def test_customer_defaults_to_empty_string(self):
		"""Should default to empty string when no customer."""
		deal = _make_deal()

		facts = _gather_facts(deal.name)

		self.assertEqual(facts["custom_customer"], "")

	def test_counts_linked_total(self):
		"""Should count all linked records."""
		deal = _make_deal()
		_make_project(deal.name)
		_make_location(deal.name)
		_make_note(deal.name)
		_make_task(deal.name)

		facts = _gather_facts(deal.name)

		# Should count: 1 project + 1 location + 1 note + 1 task = 4
		self.assertEqual(facts["linked_total"], 4)


class TestPickSurvivor(ERPNextTestSuite):
	"""Tests for _pick_survivor helper"""

	def test_picks_deal_with_most_projects(self):
		"""Deal with most projects should win."""
		deal1 = _make_deal(hubspot_id="hs_test_001")
		deal2 = _make_deal(hubspot_id="hs_test_001")

		_make_project(deal1.name)
		_make_project(deal1.name)
		_make_project(deal2.name)

		facts = {deal1.name: _gather_facts(deal1.name), deal2.name: _gather_facts(deal2.name)}
		survivor = _pick_survivor([deal1.name, deal2.name], facts)

		self.assertEqual(survivor, deal1.name)

	def test_picks_deal_with_customer_over_without(self):
		"""Deal with customer should win over deal without."""
		customer = _make_customer()
		deal1 = _make_deal(hubspot_id="hs_test_002")
		deal2 = _make_deal(hubspot_id="hs_test_002", customer=customer.name)

		facts = {deal1.name: _gather_facts(deal1.name), deal2.name: _gather_facts(deal2.name)}
		survivor = _pick_survivor([deal1.name, deal2.name], facts)

		self.assertEqual(survivor, deal2.name)

	def test_picks_deal_with_most_locations(self):
		"""Deal with most locations should win (when projects tied)."""
		deal1 = _make_deal(hubspot_id="hs_test_003")
		deal2 = _make_deal(hubspot_id="hs_test_003")

		_make_location(deal1.name)
		_make_location(deal1.name)
		_make_location(deal2.name)

		facts = {deal1.name: _gather_facts(deal1.name), deal2.name: _gather_facts(deal2.name)}
		survivor = _pick_survivor([deal1.name, deal2.name], facts)

		self.assertEqual(survivor, deal1.name)

	def test_picks_oldest_when_all_tied(self):
		"""Oldest deal should win when all criteria tied."""
		deal1 = _make_deal(hubspot_id="hs_test_004")
		deal2 = _make_deal(hubspot_id="hs_test_004")

		# Force deal1 to be older
		frappe.db.set_value(
			"CRM Deal",
			deal1.name,
			"creation",
			datetime.now() - timedelta(hours=1),
			update_modified=False,
		)

		# Input list is already ordered oldest-first (as _find_duplicate_groups returns)
		facts = {deal1.name: _gather_facts(deal1.name), deal2.name: _gather_facts(deal2.name)}
		survivor = _pick_survivor([deal1.name, deal2.name], facts)

		self.assertEqual(survivor, deal1.name)


class TestDedupeFiles(ERPNextTestSuite):
	"""Tests for _dedupe_survivor_files helper"""

	def test_keeps_oldest_file_deletes_duplicates(self):
		"""When two files have same name, oldest should be kept."""
		deal = _make_deal()
		file1 = _make_file(deal.name, "hs_invoice.txt")
		file2 = _make_file(deal.name, "hs_invoice.txt")

		# Force file1 to be older
		frappe.db.set_value(
			"File",
			file1.name,
			"creation",
			datetime.now() - timedelta(hours=1),
			update_modified=False,
		)

		_dedupe_survivor_files(deal.name)

		# file1 should exist, file2 should be deleted
		self.assertTrue(frappe.db.exists("File", file1.name))
		self.assertFalse(frappe.db.exists("File", file2.name))

	def test_keeps_all_files_with_different_names(self):
		"""Files with different names should all be kept."""
		deal = _make_deal()
		file1 = _make_file(deal.name, "invoice.txt")
		file2 = _make_file(deal.name, "contract.txt")

		_dedupe_survivor_files(deal.name)

		# Both should exist
		self.assertTrue(frappe.db.exists("File", file1.name))
		self.assertTrue(frappe.db.exists("File", file2.name))

	def test_noop_when_no_duplicates(self):
		"""Should be safe noop when no duplicate files."""
		deal = _make_deal()
		file1 = _make_file(deal.name, "unique.txt")

		_dedupe_survivor_files(deal.name)

		# File should still exist
		self.assertTrue(frappe.db.exists("File", file1.name))


class TestMergeGroup(ERPNextTestSuite):
	"""Tests for _merge_group"""

	def test_conflicting_projects_on_both_rows_raises(self):
		"""Two deals with different projects should raise RuntimeError."""
		deal1 = _make_deal(hubspot_id="hs_dup_005")
		deal2 = _make_deal(hubspot_id="hs_dup_005")

		deal1_name = deal1.name
		deal2_name = deal2.name

		# Create a project on each deal
		_make_project(deal1_name)
		_make_project(deal2_name)

		with self.assertRaises(RuntimeError) as ctx:
			_merge_group("hs_dup_005", [deal1_name, deal2_name])

		self.assertIn("more than one row has a linked Project", str(ctx.exception))

	def test_conflicting_customers_on_both_rows_raises(self):
		"""Two deals with different custom_customer values should raise RuntimeError."""
		customer1 = _make_customer("Cust1")
		customer2 = _make_customer("Cust2")

		deal1 = _make_deal(hubspot_id="hs_dup_006", customer=customer1.name)
		deal2 = _make_deal(hubspot_id="hs_dup_006", customer=customer2.name)

		deal1_name = deal1.name
		deal2_name = deal2.name

		with self.assertRaises(RuntimeError) as ctx:
			_merge_group("hs_dup_006", [deal1_name, deal2_name])

		self.assertIn("rows disagree on custom_customer", str(ctx.exception))

	def test_calls_rename_doc_for_each_loser(self):
		"""Should merge losers into survivor via real rename_doc."""
		deal1 = _make_deal(hubspot_id="hs_dup_007")
		deal2 = _make_deal(hubspot_id="hs_dup_007")
		deal3 = _make_deal(hubspot_id="hs_dup_007")

		# Force creation order
		frappe.db.set_value(
			"CRM Deal",
			deal1.name,
			"creation",
			datetime.now() - timedelta(hours=2),
			update_modified=False,
		)
		frappe.db.set_value(
			"CRM Deal",
			deal2.name,
			"creation",
			datetime.now() - timedelta(hours=1),
			update_modified=False,
		)

		_merge_group("hs_dup_007", [deal1.name, deal2.name, deal3.name])

		# Survivor (deal1, oldest) should exist
		self.assertTrue(frappe.db.exists("CRM Deal", deal1.name))
		# Losers (deal2, deal3) should be deleted
		self.assertFalse(frappe.db.exists("CRM Deal", deal2.name))
		self.assertFalse(frappe.db.exists("CRM Deal", deal3.name))

	def test_calls_dedupe_files_after_merge(self):
		"""Should call _dedupe_survivor_files after merging."""
		deal1 = _make_deal(hubspot_id="hs_dup_008")
		deal2 = _make_deal(hubspot_id="hs_dup_008")

		with patch(
			"ivm.integrations.hubspot.patches.merge_duplicate_crm_deals._dedupe_survivor_files"
		) as mock_dedupe:
			_merge_group("hs_dup_008", [deal1.name, deal2.name])

		mock_dedupe.assert_called_once_with(deal1.name)

	def test_survivor_prefers_row_with_project_and_project_stays_linked(self):
		"""Survivor with project should be chosen, and project stays linked."""
		deal1 = _make_deal(hubspot_id="hs_dup_013")
		deal2 = _make_deal(hubspot_id="hs_dup_013")

		# Only deal2 has a project
		project = _make_project(deal2.name)

		_merge_group("hs_dup_013", [deal1.name, deal2.name])

		# deal2 should survive (has project)
		self.assertTrue(frappe.db.exists("CRM Deal", deal2.name))
		self.assertFalse(frappe.db.exists("CRM Deal", deal1.name))
		# Project should still be linked to deal2
		project_crm_deal = frappe.db.get_value("Project", project.name, "custom_crm_deal")
		self.assertEqual(project_crm_deal, deal2.name)

	def test_merge_repoints_project_from_loser_to_survivor(self):
		"""Project linked to loser should be re-pointed to survivor."""
		deal1 = _make_deal(hubspot_id="hs_dup_014")
		deal2 = _make_deal(hubspot_id="hs_dup_014")

		# Project on deal1 (survivor) — it has project_count=1, deal2 has 0
		# So deal1 wins on project_count
		project_on_survivor = _make_project(deal1.name)

		_merge_group("hs_dup_014", [deal1.name, deal2.name])

		# deal1 should survive (has project), deal2 deleted
		self.assertTrue(frappe.db.exists("CRM Deal", deal1.name))
		self.assertFalse(frappe.db.exists("CRM Deal", deal2.name))
		# Project on survivor should still be linked to deal1
		project_crm_deal = frappe.db.get_value("Project", project_on_survivor.name, "custom_crm_deal")
		self.assertEqual(project_crm_deal, deal1.name)

	def test_merge_repoints_notes_and_tasks(self):
		"""Notes and tasks linked to loser should be re-pointed to survivor."""
		deal1 = _make_deal(hubspot_id="hs_dup_015")
		deal2 = _make_deal(hubspot_id="hs_dup_015")

		# deal1 has 2 linked records (note + task), deal2 has 1
		# So deal1 wins on linked_total
		_make_note(deal1.name)
		_make_task(deal1.name)

		# Note and task linked to deal2 (the loser)
		note = _make_note(deal2.name)
		task = _make_task(deal2.name)

		_merge_group("hs_dup_015", [deal1.name, deal2.name])

		# deal1 should survive (more linked records), deal2 deleted
		self.assertTrue(frappe.db.exists("CRM Deal", deal1.name))
		self.assertFalse(frappe.db.exists("CRM Deal", deal2.name))
		# Note and task that were on deal2 should now reference deal1 (survivor)
		note_ref = frappe.db.get_value("FCRM Note", note.name, "reference_docname")
		task_ref = frappe.db.get_value("CRM Task", task.name, "reference_docname")
		self.assertEqual(note_ref, deal1.name)
		self.assertEqual(task_ref, deal1.name)

	def test_merge_repoints_file_attachment(self):
		"""File attached to loser should be re-pointed to survivor."""
		deal1 = _make_deal(hubspot_id="hs_dup_016")
		deal2 = _make_deal(hubspot_id="hs_dup_016")

		# deal1 has 2 files, deal2 has 1
		# So deal1 wins on linked_total
		_make_file(deal1.name, "file1.txt")
		_make_file(deal1.name, "file2.txt")

		# File attached to deal2 (the loser)
		file_doc = _make_file(deal2.name, "test_attachment.txt")

		_merge_group("hs_dup_016", [deal1.name, deal2.name])

		# deal1 should survive (more linked records), deal2 deleted
		self.assertTrue(frappe.db.exists("CRM Deal", deal1.name))
		self.assertFalse(frappe.db.exists("CRM Deal", deal2.name))
		# File that was on deal2 should now be attached to deal1 (survivor)
		file_attached_to = frappe.db.get_value("File", file_doc.name, "attached_to_name")
		self.assertEqual(file_attached_to, deal1.name)


def _unique_hubspot_id():
	"""Generate a hubspot_id guaranteed not to collide with leftovers from
	earlier test runs.

	execute() calls frappe.db.commit() on success, which — unlike every other
	write in these tests — is NOT undone by ERPNextTestSuite's per-test
	rollback. Any test that lets the real execute() run to completion
	therefore leaves its CRM Deal data permanently in the site. A fixed
	literal hubspot_id (e.g. "hs_dup_009") would collide with that same
	literal's leftover row from a prior run, producing unpredictable
	3+-row groups on the next run. Generating a fresh id per test run, and
	registering explicit cleanup below, keeps this file safe to re-run
	indefinitely without accumulating junk or flaking on stale state.
	"""
	return f"hs_test_{frappe.generate_hash(length=12)}"


class TestExecute(ERPNextTestSuite):
	"""Tests for execute()

	execute() commits on success (see _unique_hubspot_id's docstring above)
	— every test here registers explicit cleanup via self.addCleanup for
	anything it creates, since ERPNextTestSuite's automatic rollback does
	not apply to already-committed rows.
	"""

	def _cleanup_hubspot_id(self, hubspot_id):
		"""Delete any CRM Deal(s) left behind under this hubspot_id, however
		many survived execute()'s merge (0, 1, or more if a bug left
		duplicates unmerged).

		execute() already committed the surviving row(s) before this
		cleanup runs, so the delete here must ALSO be committed explicitly
		— otherwise ERPNextTestSuite's own tearDown() rollback would undo
		this cleanup's delete (which was never itself committed) while
		leaving execute()'s earlier commit of the original row intact,
		silently defeating the cleanup entirely.
		"""
		for name in frappe.get_all("CRM Deal", filters={"custom_hubspot_deal_id": hubspot_id}, pluck="name"):
			frappe.delete_doc("CRM Deal", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def test_no_duplicates_is_a_noop(self):
		"""Single deal with unique hubspot_id should not be affected."""
		hubspot_id = _unique_hubspot_id()
		self.addCleanup(self._cleanup_hubspot_id, hubspot_id)
		deal = _make_deal(hubspot_id=hubspot_id)
		original_name = deal.name

		with patch("ivm.integrations.hubspot.patches.merge_duplicate_crm_deals.enqueue_sync"):
			execute()

		# Deal should still exist unchanged
		self.assertTrue(frappe.db.exists("CRM Deal", original_name))
		self.assertEqual(
			frappe.db.get_value("CRM Deal", original_name, "custom_hubspot_deal_id"),
			hubspot_id,
		)

	def test_calls_enqueue_sync_for_each_merged_group(self):
		"""Should call enqueue_sync once per merged hubspot_id."""
		hubspot_id = _unique_hubspot_id()
		self.addCleanup(self._cleanup_hubspot_id, hubspot_id)
		_make_deal(hubspot_id=hubspot_id)
		_make_deal(hubspot_id=hubspot_id)

		with patch("ivm.integrations.hubspot.patches.merge_duplicate_crm_deals.enqueue_sync") as mock_sync:
			execute()

		# Should call enqueue_sync once for this hubspot_id
		mock_sync.assert_called_once()
		call_args = mock_sync.call_args
		self.assertEqual(call_args[1]["hubspot_deal_id"], hubspot_id)

	def test_multiple_duplicate_groups_all_synced(self):
		"""Should sync all duplicate groups."""
		hubspot_id_a = _unique_hubspot_id()
		hubspot_id_b = _unique_hubspot_id()
		self.addCleanup(self._cleanup_hubspot_id, hubspot_id_a)
		self.addCleanup(self._cleanup_hubspot_id, hubspot_id_b)
		_make_deal(hubspot_id=hubspot_id_a)
		_make_deal(hubspot_id=hubspot_id_a)
		_make_deal(hubspot_id=hubspot_id_b)
		_make_deal(hubspot_id=hubspot_id_b)

		with patch("ivm.integrations.hubspot.patches.merge_duplicate_crm_deals.enqueue_sync") as mock_sync:
			execute()

		# Should call enqueue_sync twice (once per hubspot_id)
		self.assertEqual(mock_sync.call_count, 2)
		synced_ids = {call[1]["hubspot_deal_id"] for call in mock_sync.call_args_list}
		self.assertEqual(synced_ids, {hubspot_id_a, hubspot_id_b})

	def test_rerun_is_safe_noop(self):
		"""Running execute() twice should be safe — second run is a noop."""
		hubspot_id = _unique_hubspot_id()
		self.addCleanup(self._cleanup_hubspot_id, hubspot_id)
		_make_deal(hubspot_id=hubspot_id)
		_make_deal(hubspot_id=hubspot_id)

		with patch("ivm.integrations.hubspot.patches.merge_duplicate_crm_deals.enqueue_sync") as mock_sync:
			execute()
			first_call_count = mock_sync.call_count
			self.assertEqual(first_call_count, 1)

			# Second run should be noop (no duplicates left)
			execute()
			self.assertEqual(mock_sync.call_count, 1)

	def test_execute_end_to_end_repoints_and_commits(self):
		"""End-to-end: execute() merges, re-points links, and enqueues sync."""
		hubspot_id = _unique_hubspot_id()
		self.addCleanup(self._cleanup_hubspot_id, hubspot_id)
		deal1 = _make_deal(hubspot_id=hubspot_id)
		deal2 = _make_deal(hubspot_id=hubspot_id)

		# Project on deal1 (survivor) — it has project_count=1, deal2 has 0
		# So deal1 wins on project_count
		project_on_survivor = _make_project(deal1.name)

		def _cleanup_project():
			# Runs before _cleanup_hubspot_id (addCleanup is LIFO), so the
			# Project is gone before the CRM Deal delete is attempted —
			# otherwise the still-linked Project would block it. Must
			# commit for the same reason _cleanup_hubspot_id does.
			if frappe.db.exists("Project", project_on_survivor.name):
				frappe.delete_doc("Project", project_on_survivor.name, ignore_permissions=True, force=True)
				frappe.db.commit()

		self.addCleanup(_cleanup_project)

		with patch("ivm.integrations.hubspot.patches.merge_duplicate_crm_deals.enqueue_sync") as mock_sync:
			execute()

		# deal1 should survive (has project), deal2 deleted
		self.assertTrue(frappe.db.exists("CRM Deal", deal1.name))
		self.assertFalse(frappe.db.exists("CRM Deal", deal2.name))
		# Project on survivor should still be linked to deal1
		project_crm_deal = frappe.db.get_value("Project", project_on_survivor.name, "custom_crm_deal")
		self.assertEqual(project_crm_deal, deal1.name)
		# enqueue_sync should be called once with the shared hubspot_id
		mock_sync.assert_called_once()
		call_args = mock_sync.call_args
		self.assertEqual(call_args[1]["hubspot_deal_id"], hubspot_id)
