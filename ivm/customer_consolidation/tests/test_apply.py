"""Tests for ivm.customer_consolidation.apply"""

import csv
import os
import random
import tempfile
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation.apply import (
	_APPLIED_HASH_KEY,
	_DISABLE_APPLIED_HASH_KEY,
	_build_active_duplicate_name_index,
	_build_customer_activity_counts,
	_build_name_candidate_index,
	_decisions_file_hash,
	_disable_file_hash,
	_find_name_candidates,
	_names_resemble,
	_set_related_customers,
	apply_assignments,
	apply_customer_disables_on_migrate,
	apply_customer_record_ids,
	apply_record_reassignments,
	create_missing_customers,
	disable_decided_customers,
	execute_merges,
	refresh_match_proposals,
	rename_customers_from_csv,
	set_customer_icorp_client_ids,
	sync_icorp_client_links,
)
from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	get_merge_conflicts,
	save_merge_resolutions,
)


def _make_customer(name_hint="Cust", **extra):
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"{name_hint}_{frappe.generate_hash(length=8)}",
			"customer_group": "_Test Customer Group",
			"territory": "All Territories",
			**extra,
		}
	).insert(ignore_permissions=True)
	return doc


def _make_icorp_client_link(client_id=None, customer=None, parent_client=None):
	# Real iCorp client ids are always numeric, and parse_legacy_client_id only recognizes
	# numeric Project.client_id values as valid evidence — a hex hash here would silently fail
	# to match, so use random digits rather than frappe.generate_hash's hex output.
	client_id = client_id or "".join(random.choices("0123456789", k=7))
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": client_id,
			"client_name": f"Client {client_id}",
			"is_active": 1,
			"customer": customer or "",
			"parent_client": parent_client or "",
		}
	).insert(ignore_permissions=True)
	return doc


class TestDecisionsFileHash(ERPNextTestSuite):
	"""_decisions_file_hash"""

	def test_same_content_same_hash(self):
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f1:
			f1.write("a,b\n1,2\n")
			path1 = f1.name
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f2:
			f2.write("x,y\n3,4\n")
			path2 = f2.name
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f3:
			f3.write("customer_a,customer_b\nA,B\n")
			path3 = f3.name

		import ivm.customer_consolidation.decisions as decisions_module

		original_merges_path = decisions_module.CUSTOMER_MERGES_PATH
		original_assignments_path = decisions_module.CLIENT_ASSIGNMENTS_PATH
		original_pairs_path = decisions_module.CUSTOMER_DISTINCT_PAIRS_PATH
		try:
			decisions_module.CUSTOMER_MERGES_PATH = path1
			decisions_module.CLIENT_ASSIGNMENTS_PATH = path2
			decisions_module.CUSTOMER_DISTINCT_PAIRS_PATH = path3
			hash1 = _decisions_file_hash()
			hash2 = _decisions_file_hash()
			self.assertEqual(hash1, hash2)

			with open(path1, "a") as f:
				f.write("5,6\n")
			hash3 = _decisions_file_hash()
			self.assertNotEqual(hash1, hash3)

			with open(path1) as f:
				f.seek(0)
				f.read()
			with open(path3, "a") as f:
				f.write("C,D,1,\n")
			hash4 = _decisions_file_hash()
			self.assertNotEqual(hash3, hash4)
		finally:
			decisions_module.CUSTOMER_MERGES_PATH = original_merges_path
			decisions_module.CLIENT_ASSIGNMENTS_PATH = original_assignments_path
			decisions_module.CUSTOMER_DISTINCT_PAIRS_PATH = original_pairs_path
			os.remove(path1)
			os.remove(path2)
			os.remove(path3)


class TestApplyOnMigrateRetry(ERPNextTestSuite):
	"""apply_on_migrate: the hash is only saved when everything applies cleanly, so a blocked
	merge or invalid assignment retries on the next migrate instead of being silently treated as
	done."""

	def _temp_decision_files(
		self,
		merges_rows=None,
		assignment_rows=None,
		pairs_rows=None,
		customers_to_create_rows=None,
		record_reassignment_rows=None,
	):
		"""Writes temp CSVs AND patches the module-level loader functions (not just the path
		constants). decisions.load_customer_merges(path=CUSTOMER_MERGES_PATH) and
		load_client_assignments(path=CLIENT_ASSIGNMENTS_PATH) bind their default path argument at
		module-definition time, so a bare `execute_merges(dry_run=False)` / `apply_assignments()`
		call (no explicit merges=/assignments=, exactly how apply_on_migrate calls them) ignores
		a patched path constant and reads the REAL repo CSV instead — which on a long-running
		shared site can contain real pending merges/assignments for Customers that don't exist on
		this site, silently making every test in this class see non-empty skipped_merges /
		invalid_assignments regardless of what this helper intends to set up. Patching the loader
		functions themselves sidesteps the bound-default problem entirely."""
		from unittest.mock import patch as _patch

		import ivm.customer_consolidation.decisions as decisions_module

		merges_rows = merges_rows or []
		assignment_rows = assignment_rows or []
		pairs_rows = pairs_rows or []
		customers_to_create_rows = customers_to_create_rows or []
		record_reassignment_rows = record_reassignment_rows or []

		def _as_rows(header, raw_rows):
			return [dict(zip(header, row, strict=False)) for row in raw_rows]

		merges_header = [
			"merge_from",
			"merge_into",
			"evidence",
			"merge_considerations",
			"field_resolutions",
			"source_client_id",
		]
		assignments_header = ["client_id", "customer", "evidence"]
		pairs_header = ["customer_a", "customer_b", "client_id", "note"]
		customers_to_create_header = [
			"customer_name",
			"customer_type",
			"customer_group",
			"territory",
			"source_client_id",
			"note",
		]
		record_reassignments_header = ["doctype", "name", "field", "from_customer", "to_customer", "evidence"]
		renames_header = [
			"current_name",
			"proposed_name",
			"confidence",
			"evidence",
			"status",
			"depends_on_merge",
			"notes",
		]

		merge_dicts = _as_rows(merges_header, merges_rows)
		assignment_dicts = _as_rows(assignments_header, assignment_rows)
		pair_set = {frozenset({r[0], r[1]}) for r in pairs_rows} if pairs_rows else set()
		customers_to_create_dicts = _as_rows(customers_to_create_header, customers_to_create_rows)
		record_reassignment_dicts = _as_rows(record_reassignments_header, record_reassignment_rows)

		patchers = [
			_patch.object(decisions_module, "load_customer_merges", return_value=merge_dicts),
			_patch.object(decisions_module, "load_client_assignments", return_value=assignment_dicts),
			_patch.object(decisions_module, "load_distinct_pairs", return_value=pair_set),
			_patch.object(
				decisions_module, "load_customers_to_create", return_value=customers_to_create_dicts
			),
			_patch.object(
				decisions_module, "load_record_reassignments", return_value=record_reassignment_dicts
			),
		]
		for p in patchers:
			p.start()
			self.addCleanup(p.stop)

		# Also write real temp files and patch the path constants, so any code that reads the
		# path directly (rather than through a loader function) still sees isolated content.
		paths = {}
		originals = {}
		for attr, (header, rows) in {
			"CUSTOMER_MERGES_PATH": (merges_header, merges_rows),
			"CLIENT_ASSIGNMENTS_PATH": (assignments_header, assignment_rows),
			"CUSTOMER_DISTINCT_PAIRS_PATH": (pairs_header, pairs_rows),
			"CUSTOMERS_TO_CREATE_PATH": (customers_to_create_header, customers_to_create_rows),
			"RECORD_REASSIGNMENTS_PATH": (record_reassignments_header, record_reassignment_rows),
			# Empty on purpose: apply_on_migrate would otherwise read the real customer_renames.csv.
			"CUSTOMER_RENAMES_PATH": (renames_header, []),
		}.items():
			with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
				writer = csv.writer(f)
				writer.writerow(header)
				for row in rows:
					writer.writerow(row)
				paths[attr] = f.name
			originals[attr] = getattr(decisions_module, attr)
			setattr(decisions_module, attr, paths[attr])

		def _restore():
			for attr, path in paths.items():
				setattr(decisions_module, attr, originals[attr])
				os.remove(path)

		self.addCleanup(_restore)
		return paths

	def test_blocked_merge_leaves_hash_unsaved(self):
		survivor = _make_customer("RetrySurvivor")
		frappe.db.set_value("Customer", survivor.name, "website", "https://survivor.example")
		loser = _make_customer("RetryLoser")
		frappe.db.set_value("Customer", loser.name, "website", "https://loser.example")

		self._temp_decision_files(merges_rows=[[loser.name, survivor.name, "", "", "", ""]])

		original_hash_value = frappe.db.get_default(_APPLIED_HASH_KEY)
		frappe.db.set_default(_APPLIED_HASH_KEY, "not-the-real-hash")
		self.addCleanup(lambda: frappe.db.set_default(_APPLIED_HASH_KEY, original_hash_value or ""))

		import ivm.customer_consolidation.apply as apply_module

		original_fetch = apply_module.fetch_icorp_clients
		apply_module.fetch_icorp_clients = lambda: []
		self.addCleanup(lambda: setattr(apply_module, "fetch_icorp_clients", original_fetch))

		with (
			patch.object(apply_module, "_icorp_is_configured", return_value=True),
			self.assertRaises(frappe.ValidationError),
		):
			apply_module.apply_on_migrate()

		self.assertTrue(frappe.db.exists("Customer", survivor.name))
		self.assertTrue(frappe.db.exists("Customer", loser.name))
		saved_hash = frappe.db.get_default(_APPLIED_HASH_KEY)
		self.assertNotEqual(saved_hash, apply_module._decisions_file_hash())

	def test_invalid_assignment_leaves_hash_unsaved(self):
		self._temp_decision_files(
			assignment_rows=[["nonexistent-client-id", "Nonexistent Customer Inc", "test"]]
		)

		original_hash_value = frappe.db.get_default(_APPLIED_HASH_KEY)
		frappe.db.set_default(_APPLIED_HASH_KEY, "not-the-real-hash")
		self.addCleanup(lambda: frappe.db.set_default(_APPLIED_HASH_KEY, original_hash_value or ""))

		import ivm.customer_consolidation.apply as apply_module

		original_fetch = apply_module.fetch_icorp_clients
		apply_module.fetch_icorp_clients = lambda: []
		self.addCleanup(lambda: setattr(apply_module, "fetch_icorp_clients", original_fetch))

		with (
			patch.object(apply_module, "_icorp_is_configured", return_value=True),
			self.assertRaises(frappe.ValidationError),
		):
			apply_module.apply_on_migrate()

		saved_hash = frappe.db.get_default(_APPLIED_HASH_KEY)
		self.assertNotEqual(saved_hash, apply_module._decisions_file_hash())

	def test_clean_run_saves_hash(self):
		self._temp_decision_files()

		original_hash_value = frappe.db.get_default(_APPLIED_HASH_KEY)
		frappe.db.set_default(_APPLIED_HASH_KEY, "not-the-real-hash")
		self.addCleanup(lambda: frappe.db.set_default(_APPLIED_HASH_KEY, original_hash_value or ""))

		import ivm.customer_consolidation.apply as apply_module

		original_fetch = apply_module.fetch_icorp_clients
		apply_module.fetch_icorp_clients = lambda: []
		self.addCleanup(lambda: setattr(apply_module, "fetch_icorp_clients", original_fetch))

		with patch.object(apply_module, "_icorp_is_configured", return_value=True):
			apply_module.apply_on_migrate()

		saved_hash = frappe.db.get_default(_APPLIED_HASH_KEY)
		self.assertEqual(saved_hash, apply_module._decisions_file_hash())


class TestExecuteMerges(ERPNextTestSuite):
	"""execute_merges"""

	def test_merge_copies_fields_carries_over_child_table_and_deletes_losing_record(self):
		survivor = _make_customer("Survivor", website="")
		losing = _make_customer("Losing", website="https://example.com")

		# a Party Account row on the losing side only — should be carried over, not lost
		losing.append("accounts", {"company": frappe.db.get_value("Company", {}, "name"), "account": None})
		losing.save(ignore_permissions=True)

		merges = [
			{
				"merge_from": losing.name,
				"merge_into": survivor.name,
				"evidence": "test",
				"merge_considerations": "",
				"field_resolutions": "",
			}
		]

		results = execute_merges(merges=merges)

		self.assertEqual(len(results), 1)
		self.assertEqual(results[0]["action"], "merged")
		self.assertFalse(frappe.db.exists("Customer", losing.name))
		self.assertEqual(frappe.db.get_value("Customer", survivor.name, "website"), "https://example.com")

		survivor_accounts = frappe.get_all(
			"Party Account", filters={"parent": survivor.name, "parenttype": "Customer"}
		)
		self.assertGreaterEqual(len(survivor_accounts), 1)

	def test_merge_with_unresolved_conflict_is_skipped(self):
		survivor = _make_customer("Survivor", website="https://b.com")
		losing = _make_customer("Losing", website="https://a.com")

		merges = [
			{
				"merge_from": losing.name,
				"merge_into": survivor.name,
				"evidence": "test",
				"merge_considerations": "",
				"field_resolutions": "",
			}
		]

		results = execute_merges(merges=merges)

		self.assertEqual(results[0]["action"], "skipped")
		self.assertIn("unresolved_field_conflicts", results[0])
		self.assertTrue(frappe.db.exists("Customer", losing.name))

	def test_already_applied_merge_is_skipped_without_error(self):
		survivor = _make_customer("Survivor")
		merges = [
			{
				"merge_from": "Some Deleted Customer",
				"merge_into": survivor.name,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
			}
		]

		results = execute_merges(merges=merges)

		self.assertEqual(results[0]["status"], "already_applied")
		self.assertEqual(results[0]["action"], "skipped")

	def test_invalid_merges_included_with_reason_and_logged_once(self):
		# merge_into doesn't exist either, so these are genuinely invalid (not already_applied)
		target = f"Ghost Target {frappe.generate_hash(length=8)}"
		merges = [
			{
				"merge_from": "Ghost A",
				"merge_into": target,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
			},
			{
				"merge_from": "Ghost B",
				"merge_into": target,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
			},
		]

		with patch.object(frappe, "log_error") as log_error:
			results = execute_merges(merges=merges)

		self.assertEqual([r["status"] for r in results], ["invalid", "invalid"])
		self.assertEqual([r["action"] for r in results], ["skipped", "skipped"])
		self.assertIn("does not exist", results[0]["reason"])
		self.assertIn("does not exist", results[1]["reason"])
		log_error.assert_called_once()

	def test_invalid_merges_in_preview_included_but_not_logged(self):
		target = f"Ghost Target {frappe.generate_hash(length=8)}"
		merges = [
			{
				"merge_from": "Ghost A",
				"merge_into": target,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
			},
		]

		with patch.object(frappe, "log_error") as log_error:
			results = execute_merges(dry_run=True, merges=merges)

		self.assertEqual(results[0]["status"], "invalid")
		self.assertIn("does not exist", results[0]["reason"])
		log_error.assert_not_called()

	def test_unknown_field_resolution_is_skipped_not_fatal(self):
		survivor = _make_customer("SurvivorSkipRes", website="")
		losing = _make_customer("LosingSkipRes", website="https://example.com")

		merges = [
			{
				"merge_from": losing.name,
				"merge_into": survivor.name,
				"evidence": "test",
				"merge_considerations": "",
				"field_resolutions": '{"not_a_real_field": "x"}',
			}
		]

		results = execute_merges(merges=merges)

		self.assertEqual(results[0]["action"], "merged")
		self.assertIn("not_a_real_field", results[0]["skipped_resolutions"])
		self.assertFalse(frappe.db.exists("Customer", losing.name))


class TestApplyAssignments(ERPNextTestSuite):
	"""apply_assignments"""

	def test_valid_assignment_sets_customer_and_source(self):
		customer = _make_customer("AssignTarget")
		link = _make_icorp_client_link()

		assignments = [{"client_id": link.icorp_client_id, "customer": customer.name, "evidence": "test"}]
		results = apply_assignments(assignments=assignments, merges=[])

		self.assertEqual(results[0]["action"], "assigned")
		updated = frappe.db.get_value(
			"iCorp Client Link", link.name, ["customer", "assignment_source"], as_dict=True
		)
		self.assertEqual(updated["customer"], customer.name)
		self.assertEqual(updated["assignment_source"], "Manual decision")

	def test_invalid_assignment_unknown_client_reported(self):
		customer = _make_customer("AssignTarget2")
		assignments = [{"client_id": "nonexistent-999", "customer": customer.name, "evidence": ""}]
		results = apply_assignments(assignments=assignments, merges=[])

		self.assertEqual(results[0]["status"], "invalid")
		self.assertIn("does not exist", results[0]["reason"])

	def test_customer_form_source_is_skipped_live(self):
		customer = _make_customer("AssignLive")
		link = _make_icorp_client_link()
		frappe.db.set_value("iCorp Client Link", link.name, "assignment_source", "Customer form")

		assignments = [{"client_id": link.icorp_client_id, "customer": customer.name, "evidence": "test"}]
		results = apply_assignments(assignments=assignments, merges=[])

		self.assertEqual(results[0]["action"], "skipped_live")
		updated = frappe.db.get_value(
			"iCorp Client Link", link.name, ["customer", "assignment_source"], as_dict=True
		)
		self.assertFalse(updated["customer"])
		self.assertEqual(updated["assignment_source"], "Customer form")

	def test_already_assigned_to_same_customer_is_already_applied_and_not_written(self):
		customer = _make_customer("AssignAlreadyApplied")
		link = _make_icorp_client_link(customer=customer.name)
		frappe.db.set_value("iCorp Client Link", link.name, "assignment_source", "Customer record")

		assignments = [{"client_id": link.icorp_client_id, "customer": customer.name, "evidence": "test"}]

		preview = apply_assignments(dry_run=True, assignments=assignments, merges=[])
		self.assertEqual(preview[0]["action"], "already_applied")

		executed = apply_assignments(dry_run=False, assignments=assignments, merges=[])
		self.assertEqual(executed[0]["action"], "already_applied")

		# no-op: assignment_source must not be rewritten to "Manual decision"
		updated = frappe.db.get_value(
			"iCorp Client Link", link.name, ["customer", "assignment_source"], as_dict=True
		)
		self.assertEqual(updated["customer"], customer.name)
		self.assertEqual(updated["assignment_source"], "Customer record")

	def test_invalid_assignments_logged_once_per_run(self):
		customer = _make_customer("AssignLogOnce")
		assignments = [
			{"client_id": "nonexistent-1", "customer": customer.name, "evidence": ""},
			{"client_id": "nonexistent-2", "customer": customer.name, "evidence": ""},
		]

		with patch.object(frappe, "log_error") as log_error:
			results = apply_assignments(assignments=assignments, merges=[])

		self.assertEqual([r["status"] for r in results], ["invalid", "invalid"])
		self.assertTrue(all(r["reason"] for r in results))
		log_error.assert_called_once()


class TestApplyRecordReassignments(ERPNextTestSuite):
	"""apply_record_reassignments"""

	def test_reassigns_and_is_idempotent_on_rerun(self):
		from_customer = _make_customer("ReassignFrom")
		to_customer = _make_customer("ReassignTo")
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "test issue",
				"issue_type": "IT",
				"customer": from_customer.name,
			}
		).insert(ignore_permissions=True)

		rows = [
			{
				"doctype": "Issue",
				"name": issue.name,
				"field": "customer",
				"from_customer": from_customer.name,
				"to_customer": to_customer.name,
				"evidence": "test",
			}
		]

		results = apply_record_reassignments(rows=rows, merges=[])
		self.assertEqual(results[0]["action"], "reassigned")
		self.assertEqual(frappe.db.get_value("Issue", issue.name, "customer"), to_customer.name)

		# rerun: already at to_customer, so it's a no-op, not an error
		results_again = apply_record_reassignments(rows=rows, merges=[])
		self.assertEqual(results_again[0]["action"], "already_applied")

	def test_refuses_when_current_value_has_changed(self):
		from_customer = _make_customer("ChangedFrom")
		to_customer = _make_customer("ChangedTo")
		someone_else = _make_customer("ChangedElse")
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "test issue",
				"issue_type": "IT",
				"customer": someone_else.name,
			}
		).insert(ignore_permissions=True)

		rows = [
			{
				"doctype": "Issue",
				"name": issue.name,
				"field": "customer",
				"from_customer": from_customer.name,
				"to_customer": to_customer.name,
				"evidence": "test",
			}
		]
		results = apply_record_reassignments(rows=rows, merges=[])

		self.assertEqual(results[0]["action"], "changed")
		self.assertEqual(frappe.db.get_value("Issue", issue.name, "customer"), someone_else.name)

	def test_missing_record_reported_not_raised(self):
		to_customer = _make_customer("MissingTo")
		rows = [
			{
				"doctype": "Issue",
				"name": "ISS-DOES-NOT-EXIST",
				"field": "customer",
				"from_customer": "Anyone",
				"to_customer": to_customer.name,
				"evidence": "test",
			}
		]
		results = apply_record_reassignments(rows=rows, merges=[])
		self.assertEqual(results[0]["action"], "missing")

	def test_invalid_row_reported_not_applied(self):
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": "test issue",
				"issue_type": "IT",
			}
		).insert(ignore_permissions=True)
		rows = [
			{
				"doctype": "Issue",
				"name": issue.name,
				"field": "customer",
				"from_customer": "",
				"to_customer": "Ghost-Customer-Does-Not-Exist",
				"evidence": "",
			}
		]
		results = apply_record_reassignments(rows=rows, merges=[])
		self.assertEqual(results[0]["status"], "invalid")
		self.assertIn("does not exist", results[0]["reason"])


class TestSetCustomerIcorpClientIds(ERPNextTestSuite):
	"""set_customer_icorp_client_ids"""

	def test_single_top_level_client_sets_icorp_client_id(self):
		customer = _make_customer("SingleTopLevel")
		link = _make_icorp_client_link(customer=customer.name)

		results = set_customer_icorp_client_ids(dry_run=True)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "set")
		self.assertEqual(match["icorp_client_id"], link.icorp_client_id)

	def test_two_top_level_clients_left_ambiguous(self):
		customer = _make_customer("TwoTopLevel")
		_make_icorp_client_link(customer=customer.name)
		_make_icorp_client_link(customer=customer.name)

		results = set_customer_icorp_client_ids(dry_run=True)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "ambiguous")
		self.assertEqual(len(match["candidates"]), 2)

	def test_location_client_not_counted_as_second_top_level(self):
		customer = _make_customer("LocationNotCounted")
		master_link = _make_icorp_client_link(customer=customer.name)
		_make_icorp_client_link(customer=customer.name, parent_client=master_link.icorp_client_id)

		results = set_customer_icorp_client_ids(dry_run=True)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "set")
		self.assertEqual(match["icorp_client_id"], master_link.icorp_client_id)

	def test_existing_value_never_overwritten(self):
		link = _make_icorp_client_link()
		customer = _make_customer("HasIdAlready", icorp_client_id=link.icorp_client_id)
		_make_icorp_client_link(customer=customer.name)  # a second, different top-level client

		results = set_customer_icorp_client_ids(dry_run=False)

		self.assertFalse(any(r["customer"] == customer.name for r in results))
		self.assertEqual(
			frappe.db.get_value("Customer", customer.name, "icorp_client_id"), link.icorp_client_id
		)

	def test_collision_with_another_customer_reported_not_written(self):
		holder = _make_customer("Holder")
		link = _make_icorp_client_link(customer=holder.name)
		frappe.db.set_value("Customer", holder.name, "icorp_client_id", link.icorp_client_id)

		seeker = _make_customer("Seeker")
		frappe.db.set_value("iCorp Client Link", link.name, "customer", seeker.name)

		results = set_customer_icorp_client_ids(dry_run=False)

		match = next(r for r in results if r["customer"] == seeker.name)
		self.assertEqual(match["action"], "collision")
		self.assertEqual(match["held_by"], holder.name)
		self.assertFalse(frappe.db.get_value("Customer", seeker.name, "icorp_client_id"))


class TestApplyCustomerRecordIds(ERPNextTestSuite):
	"""apply_customer_record_ids"""

	def test_matching_name_assigns_link_to_customer(self):
		customer = _make_customer("MetaLike")
		frappe.db.set_value("Customer", customer.name, "customer_name", "Meta")
		link = _make_icorp_client_link()
		frappe.db.set_value("iCorp Client Link", link.name, "client_name", "Meta")
		frappe.db.set_value("Customer", customer.name, "icorp_client_id", link.icorp_client_id)
		frappe.db.commit()

		results = apply_customer_record_ids(dry_run=False)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "assigned")
		self.assertEqual(frappe.db.get_value("iCorp Client Link", link.name, "customer"), customer.name)
		self.assertEqual(
			frappe.db.get_value("iCorp Client Link", link.name, "assignment_source"), "Customer record"
		)

	def test_mismatched_name_skipped_and_left_unassigned(self):
		customer = _make_customer("USNavyLike")
		frappe.db.set_value("Customer", customer.name, "customer_name", "US Navy")
		link = _make_icorp_client_link()
		frappe.db.set_value("iCorp Client Link", link.name, "client_name", "Kijero, LLC.")
		frappe.db.set_value("Customer", customer.name, "icorp_client_id", link.icorp_client_id)
		frappe.db.commit()

		results = apply_customer_record_ids(dry_run=False)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "name_mismatch")
		self.assertFalse(frappe.db.get_value("iCorp Client Link", link.name, "customer"))

	def test_already_assigned_link_left_untouched(self):
		customer = _make_customer("AlreadyAssignedCo")
		other_customer = _make_customer("SomeoneElse")
		link = _make_icorp_client_link(customer=other_customer.name)
		frappe.db.set_value("iCorp Client Link", link.name, "client_name", customer.customer_name)
		frappe.db.set_value("Customer", customer.name, "icorp_client_id", link.icorp_client_id)
		frappe.db.commit()

		results = apply_customer_record_ids(dry_run=False)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "already_assigned")
		self.assertTrue(match["conflict"])
		self.assertEqual(frappe.db.get_value("iCorp Client Link", link.name, "customer"), other_customer.name)


class TestNamesResemble(ERPNextTestSuite):
	"""_names_resemble"""

	def test_identical_names_match(self):
		self.assertTrue(_names_resemble("Meta", "Meta"))

	def test_same_full_name_matches(self):
		self.assertTrue(_names_resemble("US Navy - PSNS & IMF (Code 109)", "US Navy - PSNS & IMF (Code 109)"))

	def test_unrelated_names_do_not_match(self):
		self.assertFalse(_names_resemble("Kijero, LLC.", "US Navy"))

	def test_blank_name_does_not_match(self):
		self.assertFalse(_names_resemble("", "Meta"))
		self.assertFalse(_names_resemble("Meta", None))


class TestNameCandidates(ERPNextTestSuite):
	"""_build_name_candidate_index / _find_name_candidates — hybrid first-token + Jaccard rule"""

	def test_first_token_match_found(self):
		customers = [{"name": "Microsoft", "customer_name": "Microsoft"}]
		index = _build_name_candidate_index(customers)
		candidates = _find_name_candidates("Microsoft Lockers Kiosks", index, {}, set())
		self.assertIn("Microsoft", candidates)

	def test_jaccard_match_found_without_shared_first_word(self):
		customers = [{"name": "Dell USA L.P", "customer_name": "Dell USA L.P"}]
		index = _build_name_candidate_index(customers)
		candidates = _find_name_candidates("Dell USA", index, {}, set())
		self.assertIn("Dell USA L.P", candidates)

	def test_generic_first_word_not_matched_alone(self):
		# "home" starts many Customer names in real data; simulate that here with > the
		# frequency threshold so a loose single-word overlap doesn't fire.
		customers = [{"name": f"Home {i}", "customer_name": f"Home {i}"} for i in range(15)]
		customers.append({"name": "Home Depot", "customer_name": "Home Depot"})
		index = _build_name_candidate_index(customers)
		candidates = _find_name_candidates("Home Chef", index, {}, set())
		self.assertNotIn("Home Depot", candidates)

	def test_excluded_names_not_returned(self):
		customers = [{"name": "Microsoft", "customer_name": "Microsoft"}]
		index = _build_name_candidate_index(customers)
		candidates = _find_name_candidates("Microsoft Lockers", index, {}, {"Microsoft"})
		self.assertEqual(candidates, [])

	def test_ranked_by_activity_descending(self):
		customers = [
			{"name": "Microsoft Kiosk", "customer_name": "Microsoft Kiosk"},
			{"name": "Microsoft", "customer_name": "Microsoft"},
		]
		index = _build_name_candidate_index(customers)
		activity = {
			"Microsoft Kiosk": {"projects": 1, "issues": 0},
			"Microsoft": {"projects": 10, "issues": 40},
		}
		candidates = _find_name_candidates("Microsoft Lockers", index, activity, set())
		self.assertEqual(candidates[0], "Microsoft")

	def test_no_match_returns_empty(self):
		customers = [{"name": "Totally Unrelated Co", "customer_name": "Totally Unrelated Co"}]
		index = _build_name_candidate_index(customers)
		candidates = _find_name_candidates("Zorblax Industries", index, {}, set())
		self.assertEqual(candidates, [])


class TestPartnerSuspectDetection(ERPNextTestSuite):
	"""refresh_match_proposals: the Zones/Microsoft/Altria pattern — a client whose only
	evidence is Project usage matching its iCorp parent's own Customer."""

	def test_project_only_matching_parents_customer_becomes_partner_suspect(self):
		# refresh_match_proposals() commits internally (by design, matching the real
		# merge/assignment functions), so this test can't rely on ERPNextTestSuite's rollback
		# for isolation — use random ids and explicitly clean up afterward.
		partner = _make_customer("ZonesLike")
		parent_link = _make_icorp_client_link(customer=partner.name)
		child_link = _make_icorp_client_link(parent_client=parent_link.icorp_client_id)
		frappe.db.set_value("iCorp Client Link", child_link.name, "client_name", "Microsoft Lockers Kiosks")

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_type": "Internal",
				"project_name": f"TestProj_{frappe.generate_hash(length=8)}",
				"customer": partner.name,
				"client_id": child_link.icorp_client_id,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Project", project.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", child_link.name, force=True, ignore_permissions=True
			)
		)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", parent_link.name, force=True, ignore_permissions=True
			)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", partner.name, force=True, ignore_permissions=True)
		)

		refresh_match_proposals()

		child = frappe.db.get_value(
			"iCorp Client Link",
			child_link.name,
			["match_status", "proposed_customer", "parent_customer"],
			as_dict=True,
		)
		self.assertEqual(child["match_status"], "partner_suspect")
		self.assertEqual(child["proposed_customer"], "")
		self.assertEqual(child["parent_customer"], partner.name)

	def test_parent_itself_still_confirms_normally(self):
		"""The parent client's own row (970 Zones, in the real case) should not be affected —
		only children whose only evidence matches the parent's customer."""
		partner = _make_customer("ZonesLike2")
		parent_link = _make_icorp_client_link(customer=partner.name)

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_type": "Internal",
				"project_name": f"TestProj_{frappe.generate_hash(length=8)}",
				"customer": partner.name,
				"client_id": parent_link.icorp_client_id,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Project", project.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", parent_link.name, force=True, ignore_permissions=True
			)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", partner.name, force=True, ignore_permissions=True)
		)

		refresh_match_proposals()

		parent_after = frappe.db.get_value("iCorp Client Link", parent_link.name, "match_status")
		self.assertNotEqual(parent_after, "partner_suspect")


class TestActiveDuplicateNameIndex(ERPNextTestSuite):
	"""_build_active_duplicate_name_index"""

	def test_two_active_clients_same_name_are_siblings(self):
		clients = [
			{"id": "1341", "name": "USAA", "is_active": True},
			{"id": "1343", "name": "USAA", "is_active": True},
		]
		index = _build_active_duplicate_name_index(clients)
		self.assertEqual(sorted(index["usaa"]), ["1341", "1343"])

	def test_inactive_duplicate_not_included(self):
		"""An inactive duplicate isn't a live collision — it shouldn't show up at all."""
		clients = [
			{"id": "1341", "name": "USAA", "is_active": True},
			{"id": "1343", "name": "USAA", "is_active": False},
		]
		index = _build_active_duplicate_name_index(clients)
		self.assertEqual(index["usaa"], ["1341"])

	def test_unique_name_has_no_siblings_entry_beyond_itself(self):
		clients = [{"id": "1622", "name": "Warburg Pincus", "is_active": True}]
		index = _build_active_duplicate_name_index(clients)
		self.assertEqual(index["warburg pincus"], ["1622"])


class TestDuplicateNameSiblingsInRefresh(ERPNextTestSuite):
	"""refresh_match_proposals: duplicate_name_siblings is populated for live naming collisions
	and excludes inactive duplicates — mirrors the real USAA 1341/1343 case."""

	def test_active_sibling_surfaced_inactive_sibling_excluded(self):
		customer = _make_customer("SiblingTest")
		client_id = "".join(random.choices("0123456789", k=7))

		active_link = _make_icorp_client_link(client_id=client_id, customer=customer.name)
		frappe.db.set_value("iCorp Client Link", active_link.name, "client_name", "Sibling Co")

		inactive_link = _make_icorp_client_link()
		frappe.db.set_value(
			"iCorp Client Link", inactive_link.name, {"client_name": "Sibling Co", "is_active": 0}
		)

		active_sibling_id = "".join(random.choices("0123456789", k=7))
		active_sibling = _make_icorp_client_link(client_id=active_sibling_id)
		frappe.db.set_value("iCorp Client Link", active_sibling.name, "client_name", "Sibling Co")

		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", active_link.name, force=True, ignore_permissions=True
			)
		)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", inactive_link.name, force=True, ignore_permissions=True
			)
		)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", active_sibling.name, force=True, ignore_permissions=True
			)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		refresh_match_proposals()

		siblings = frappe.db.get_value("iCorp Client Link", active_link.name, "duplicate_name_siblings")
		self.assertIn(active_sibling.icorp_client_id, siblings)
		self.assertNotIn(inactive_link.icorp_client_id, siblings)


class TestSetRelatedCustomers(ERPNextTestSuite):
	"""_set_related_customers"""

	def _related_rows(self, client_id):
		return frappe.get_all(
			"iCorp Client Link Customer Candidate",
			filters={"parent": client_id, "parenttype": "iCorp Client Link"},
			fields=["customer", "is_current_proposal", "role"],
			order_by="idx",
		)

	def test_proposed_and_candidates_written_with_correct_proposal_flag(self):
		survivor = _make_customer("Survivor")
		candidate = _make_customer("Lookalike")
		link = _make_icorp_client_link()

		_set_related_customers(link.icorp_client_id, [candidate.name], survivor.name, {})

		rows = self._related_rows(link.icorp_client_id)
		self.assertEqual(len(rows), 2)
		proposed_row = next(r for r in rows if r["customer"] == survivor.name)
		candidate_row = next(r for r in rows if r["customer"] == candidate.name)
		self.assertEqual(proposed_row["is_current_proposal"], 1)
		self.assertEqual(candidate_row["is_current_proposal"], 0)

	def test_existing_role_decision_survives_a_second_refresh(self):
		survivor = _make_customer("Survivor2")
		candidate = _make_customer("Lookalike2")
		link = _make_icorp_client_link()

		_set_related_customers(link.icorp_client_id, [candidate.name], survivor.name, {})
		frappe.db.set_value(
			"iCorp Client Link Customer Candidate",
			{"parent": link.icorp_client_id, "customer": candidate.name},
			"role",
			"Duplicate - merge in",
		)

		# simulate a routine refresh re-running with the same candidates
		_set_related_customers(link.icorp_client_id, [candidate.name], survivor.name, {})

		rows = self._related_rows(link.icorp_client_id)
		candidate_row = next(r for r in rows if r["customer"] == candidate.name)
		self.assertEqual(candidate_row["role"], "Duplicate - merge in")

	def test_activity_summary_reflects_counts(self):
		customer = _make_customer("ActivityTest")
		link = _make_icorp_client_link()
		counts = {customer.name: {"projects": 3, "issues": 7}}

		_set_related_customers(link.icorp_client_id, [], customer.name, counts)

		summary = frappe.db.get_value(
			"iCorp Client Link Customer Candidate",
			{"parent": link.icorp_client_id, "customer": customer.name},
			"activity_summary",
		)
		self.assertEqual(summary, "3 Projects, 7 Issues")


class TestSurvivorValidation(ERPNextTestSuite):
	"""iCorpClientLink.validate(): at most one 'This client's Customer' row"""

	def test_two_survivors_blocked_on_save(self):
		frappe.conf.customer_consolidation_review_site = 1
		try:
			link = _make_icorp_client_link()
			doc = frappe.get_doc("iCorp Client Link", link.name)
			doc.append(
				"related_customers", {"customer": _make_customer("A").name, "role": "This client's Customer"}
			)
			doc.append(
				"related_customers", {"customer": _make_customer("B").name, "role": "This client's Customer"}
			)

			with self.assertRaises(frappe.ValidationError):
				doc.save(ignore_permissions=True)
		finally:
			frappe.conf.customer_consolidation_review_site = 0

	def test_one_survivor_saves_fine(self):
		frappe.conf.customer_consolidation_review_site = 1
		try:
			link = _make_icorp_client_link()
			doc = frappe.get_doc("iCorp Client Link", link.name)
			doc.append(
				"related_customers", {"customer": _make_customer("C").name, "role": "This client's Customer"}
			)
			doc.save(ignore_permissions=True)  # should not raise
		finally:
			frappe.conf.customer_consolidation_review_site = 0


class TestMergeConflictResolution(ERPNextTestSuite):
	"""get_merge_conflicts / save_merge_resolutions.

	decisions.load_customer_merges(path=CUSTOMER_MERGES_PATH) binds its default argument at
	module-definition time, so patching decisions.CUSTOMER_MERGES_PATH after the fact does NOT
	change what a no-argument call to load_customer_merges() reads — these tests therefore mock
	load_customer_merges itself (so get_merge_conflicts/execute_merges's internal read sees our
	rows) while still patching CUSTOMER_MERGES_PATH (so save_merge_resolutions's _write_csv call,
	which reads the module attribute live rather than through a bound default, writes to a temp
	file instead of the real repo CSV).
	"""

	def _review_site(self):
		original = frappe.conf.get("customer_consolidation_review_site")
		frappe.conf.customer_consolidation_review_site = 1

		def _restore():
			if original is None:
				frappe.conf.pop("customer_consolidation_review_site", None)
			else:
				frappe.conf.customer_consolidation_review_site = original

		self.addCleanup(_restore)

	def test_get_merge_conflicts_groups_by_survivor(self):
		self._review_site()
		survivor = _make_customer("ConflictSurvivor")
		frappe.db.set_value("Customer", survivor.name, "customer_type", "Company")
		loser = _make_customer("ConflictLoser")
		frappe.db.set_value("Customer", loser.name, "customer_type", "Integrator")

		rows = [
			{
				"merge_from": loser.name,
				"merge_into": survivor.name,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": "",
			}
		]

		import ivm.customer_consolidation.decisions as decisions_module

		with patch.object(decisions_module, "load_customer_merges", return_value=rows):
			conflicts = get_merge_conflicts()

		match = next((c for c in conflicts if c["merge_into"] == survivor.name), None)
		self.assertIsNotNone(match)
		self.assertIn(loser.name, match["merges"])
		field_names = {f["fieldname"] for f in match["fields"]}
		self.assertIn("customer_type", field_names)

		field = next(f for f in match["fields"] if f["fieldname"] == "customer_type")
		option_customers = {o["customer"] for o in field["options"]}
		self.assertEqual(option_customers, {survivor.name, loser.name})

	def test_save_merge_resolutions_writes_chosen_value(self):
		self._review_site()
		survivor = _make_customer("SaveResSurvivor")
		frappe.db.set_value("Customer", survivor.name, "customer_type", "Company")
		loser = _make_customer("SaveResLoser")
		frappe.db.set_value("Customer", loser.name, "customer_type", "Integrator")

		rows = [
			{
				"merge_from": loser.name,
				"merge_into": survivor.name,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": "",
			}
		]

		import tempfile

		import ivm.customer_consolidation.decisions as decisions_module

		fd, temp_path = tempfile.mkstemp(suffix=".csv")
		os.close(fd)
		original_path = decisions_module.CUSTOMER_MERGES_PATH
		try:
			decisions_module.CUSTOMER_MERGES_PATH = temp_path
			with patch.object(decisions_module, "load_customer_merges", return_value=rows):
				save_merge_resolutions(
					{survivor.name: {"customer_type": {"value": "Integrator", "custom": False}}}
				)

			written_rows = decisions_module._read_csv_rows(temp_path)
			row = next(r for r in written_rows if r["merge_from"] == loser.name)
			resolved = decisions_module.parse_field_resolutions(row["field_resolutions"])
			self.assertEqual(resolved.get("customer_type"), "Integrator")
		finally:
			decisions_module.CUSTOMER_MERGES_PATH = original_path
			os.remove(temp_path)

	def test_save_merge_resolutions_rejects_invalid_custom_link_value(self):
		self._review_site()
		territories = frappe.get_all("Territory", limit=2, pluck="name")
		survivor = _make_customer("RejectSurvivor", territory=territories[0])
		loser = _make_customer("RejectLoser", territory=territories[1])

		rows = [
			{
				"merge_from": loser.name,
				"merge_into": survivor.name,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": "",
			}
		]

		import ivm.customer_consolidation.decisions as decisions_module

		with patch.object(decisions_module, "load_customer_merges", return_value=rows):
			with self.assertRaises(frappe.ValidationError):
				save_merge_resolutions(
					{
						survivor.name: {
							"territory": {"value": "DefinitelyNotARealTerritory12345", "custom": True}
						}
					}
				)


class TestCreateMissingCustomers(ERPNextTestSuite):
	"""create_missing_customers"""

	def _temp_customers_to_create_file(self, rows):
		import tempfile

		import ivm.customer_consolidation.decisions as decisions_module

		header = ["customer_name", "customer_type", "customer_group", "territory", "source_client_id", "note"]
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.writer(f)
			writer.writerow(header)
			for row in rows:
				writer.writerow(row)
			temp_path = f.name

		original = decisions_module.CUSTOMERS_TO_CREATE_PATH
		decisions_module.CUSTOMERS_TO_CREATE_PATH = temp_path

		def _restore():
			decisions_module.CUSTOMERS_TO_CREATE_PATH = original
			os.remove(temp_path)

		self.addCleanup(_restore)

	def test_creates_missing_customer(self):
		name = f"NewCustomer_{frappe.generate_hash(length=8)}"
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", name, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", name)
			else None
		)

		self._temp_customers_to_create_file([[name, "Company", "Individual", "_Test Territory", "100", ""]])

		results = create_missing_customers(dry_run=False)

		match = next(r for r in results if r["customer_name"] == name)
		self.assertEqual(match["action"], "created")
		self.assertTrue(frappe.db.exists("Customer", name))

	def test_existing_customer_left_alone(self):
		customer = _make_customer("AlreadyThere")
		self._temp_customers_to_create_file(
			[[customer.name, "Company", "Individual", "_Test Territory", "100", ""]]
		)

		results = create_missing_customers(dry_run=False)

		match = next(r for r in results if r["customer_name"] == customer.name)
		self.assertEqual(match["action"], "exists")

	def test_group_type_customer_group_is_invalid(self):
		name = f"BadGroupCustomer_{frappe.generate_hash(length=8)}"
		self._temp_customers_to_create_file(
			[[name, "Company", "All Customer Groups", "_Test Territory", "100", ""]]
		)

		results = create_missing_customers(dry_run=False)

		match = next(r for r in results if r["customer_name"] == name)
		self.assertEqual(match["action"], "invalid")
		self.assertFalse(frappe.db.exists("Customer", name))

	def test_dry_run_does_not_create(self):
		name = f"DryRunCustomer_{frappe.generate_hash(length=8)}"
		self._temp_customers_to_create_file([[name, "Company", "Individual", "_Test Territory", "100", ""]])

		results = create_missing_customers(dry_run=True)

		match = next(r for r in results if r["customer_name"] == name)
		self.assertEqual(match["action"], "would_create")
		self.assertFalse(frappe.db.exists("Customer", name))


class TestDisableDecidedCustomers(ERPNextTestSuite):
	"""disable_decided_customers"""

	def _temp_customers_to_disable_file(self, rows):
		"""Write temp CSV and patch the path constant."""
		import tempfile

		import ivm.customer_consolidation.decisions as decisions_module

		header = ["customer", "reason", "decided_by", "date_decided"]
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.writer(f)
			writer.writerow(header)
			for row in rows:
				writer.writerow(row)
			temp_path = f.name

		original = decisions_module.CUSTOMERS_TO_DISABLE_PATH
		decisions_module.CUSTOMERS_TO_DISABLE_PATH = temp_path

		def _restore():
			decisions_module.CUSTOMERS_TO_DISABLE_PATH = original
			os.remove(temp_path)

		self.addCleanup(_restore)

	def test_orphan_customer_is_disabled(self):
		customer = _make_customer("DisableOrphan")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		self._temp_customers_to_disable_file([[customer.name, "test reason", "test user", "2026-01-01"]])

		results = disable_decided_customers(dry_run=False)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "disabled")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "disabled"), 1)

	def test_already_gone_customer_reported(self):
		self._temp_customers_to_disable_file(
			[["NonexistentCustomer", "test reason", "test user", "2026-01-01"]]
		)

		results = disable_decided_customers(dry_run=False)

		match = next(r for r in results if r["customer"] == "NonexistentCustomer")
		self.assertEqual(match["action"], "already_gone")

	def test_already_disabled_customer_reported(self):
		customer = _make_customer("AlreadyDisabled", disabled=1)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		self._temp_customers_to_disable_file([[customer.name, "test reason", "test user", "2026-01-01"]])

		results = disable_decided_customers(dry_run=False)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "already_disabled")

	def test_connected_customer_still_disabled_and_flagged(self):
		customer = _make_customer("NowConnected")
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_type": "Internal",
				"project_name": f"TestProj_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Project", project.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		self._temp_customers_to_disable_file([[customer.name, "test reason", "test user", "2026-01-01"]])

		results = disable_decided_customers(dry_run=False)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "disabled_with_links")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "disabled"), 1)

	def test_dry_run_does_not_disable(self):
		customer = _make_customer("DryRunDisable")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		self._temp_customers_to_disable_file([[customer.name, "test reason", "test user", "2026-01-01"]])

		results = disable_decided_customers(dry_run=True)

		match = next(r for r in results if r["customer"] == customer.name)
		self.assertEqual(match["action"], "would_disable")
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "disabled"), 0)


class TestApplyCustomerDeletionsOnMigrate(ERPNextTestSuite):
	"""apply_customer_disables_on_migrate: hash-gate and retry logic"""

	def _temp_customers_to_disable_file(self, rows):
		"""Write temp CSV and patch both the path constant and loader function."""
		import tempfile

		import ivm.customer_consolidation.decisions as decisions_module

		header = ["customer", "reason", "decided_by", "date_decided"]
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.writer(f)
			writer.writerow(header)
			for row in rows:
				writer.writerow(row)
			temp_path = f.name

		original_path = decisions_module.CUSTOMERS_TO_DISABLE_PATH
		decisions_module.CUSTOMERS_TO_DISABLE_PATH = temp_path

		# Also patch the loader function to use our temp file
		original_loader = decisions_module.load_customers_to_disable

		def _patched_load(path=None):
			return decisions_module._read_csv_rows(temp_path)

		decisions_module.load_customers_to_disable = _patched_load

		def _restore():
			decisions_module.CUSTOMERS_TO_DISABLE_PATH = original_path
			decisions_module.load_customers_to_disable = original_loader
			os.remove(temp_path)

		self.addCleanup(_restore)

	def test_unchanged_csv_skips_entirely(self):
		self._temp_customers_to_disable_file([])

		original_hash_value = frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY)
		current_hash = _disable_file_hash()
		frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, current_hash)
		self.addCleanup(lambda: frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, original_hash_value or ""))

		apply_customer_disables_on_migrate()

		# Hash should still be the same (no change)
		self.assertEqual(frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY), current_hash)

	def test_changed_csv_with_disableable_customer_saves_hash(self):
		customer = _make_customer("HashSaveDisable")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		self._temp_customers_to_disable_file([[customer.name, "test reason", "test user", "2026-01-01"]])

		original_hash_value = frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY)
		frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, "not-the-real-hash")
		self.addCleanup(lambda: frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, original_hash_value or ""))

		# Compute expected hash from the temp file before calling apply
		import ivm.customer_consolidation.apply as apply_module

		expected_hash = apply_module._disable_file_hash()

		apply_customer_disables_on_migrate()

		saved_hash = frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY)
		self.assertEqual(saved_hash, expected_hash)
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "disabled"), 1)

	def test_connected_customer_disabled_and_hash_saved(self):
		customer = _make_customer("NoHashSaveConnected")
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_type": "Internal",
				"project_name": f"TestProj_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Project", project.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		self._temp_customers_to_disable_file([[customer.name, "test reason", "test user", "2026-01-01"]])

		original_hash_value = frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY)
		frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, "not-the-real-hash")
		self.addCleanup(lambda: frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, original_hash_value or ""))

		# Compute expected hash from the temp file
		import ivm.customer_consolidation.apply as apply_module

		expected_hash = apply_module._disable_file_hash()

		apply_customer_disables_on_migrate()

		saved_hash = frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY)
		# Operational links no longer block: the row is disabled (flagged), so the hash is saved
		self.assertEqual(saved_hash, expected_hash)
		self.assertEqual(frappe.db.get_value("Customer", customer.name, "disabled"), 1)

	def test_pending_merge_skipped_not_disabled(self):
		"""A customer that is pending merge_from should be skipped, not disabled."""
		customer_from = _make_customer("PendingMergeFrom")
		customer_into = _make_customer("PendingMergeInto")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer_from.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer_into.name, force=True, ignore_permissions=True)
		)

		# Create temp merges CSV with this customer as merge_from
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"merge_from",
					"merge_into",
					"evidence",
					"merge_considerations",
					"field_resolutions",
					"source_client_id",
				],
			)
			writer.writeheader()
			writer.writerow(
				{
					"merge_from": customer_from.name,
					"merge_into": customer_into.name,
					"evidence": "test",
					"merge_considerations": "",
					"field_resolutions": "",
					"source_client_id": "",
				}
			)
			temp_merges_path = f.name

		# Create temp deletes CSV with this customer
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(f, fieldnames=["customer", "reason", "decided_by", "date_decided"])
			writer.writeheader()
			writer.writerow(
				{
					"customer": customer_from.name,
					"reason": "test",
					"decided_by": "test",
					"date_decided": "2026-01-01",
				}
			)
			temp_deletes_path = f.name

		try:
			import ivm.customer_consolidation.decisions as decisions_module

			original_merges_path = decisions_module.CUSTOMER_MERGES_PATH
			original_deletes_path = decisions_module.CUSTOMERS_TO_DISABLE_PATH
			original_merges_loader = decisions_module.load_customer_merges
			original_deletes_loader = decisions_module.load_customers_to_disable

			def _patched_merges_load(path=None):
				return decisions_module._read_csv_rows(temp_merges_path)

			def _patched_deletes_load(path=None):
				return decisions_module._read_csv_rows(temp_deletes_path)

			decisions_module.CUSTOMER_MERGES_PATH = temp_merges_path
			decisions_module.CUSTOMERS_TO_DISABLE_PATH = temp_deletes_path
			decisions_module.load_customer_merges = _patched_merges_load
			decisions_module.load_customers_to_disable = _patched_deletes_load

			try:
				results = disable_decided_customers(dry_run=False)
				# Should have one result with action "pending_merge"
				self.assertEqual(len(results), 1)
				self.assertEqual(results[0]["action"], "pending_merge")
				# Customer should NOT be disabled
				self.assertEqual(frappe.db.get_value("Customer", customer_from.name, "disabled"), 0)
			finally:
				decisions_module.CUSTOMER_MERGES_PATH = original_merges_path
				decisions_module.CUSTOMERS_TO_DISABLE_PATH = original_deletes_path
				decisions_module.load_customer_merges = original_merges_loader
				decisions_module.load_customers_to_disable = original_deletes_loader
		finally:
			os.remove(temp_merges_path)
			os.remove(temp_deletes_path)

	def test_pending_merge_not_in_problems_list(self):
		"""pending_merge should not be included in the problems list for apply_customer_disables_on_migrate."""
		customer_from = _make_customer("PendingMergeNotProblem")
		customer_into = _make_customer("PendingMergeNotProblemInto")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer_from.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer_into.name, force=True, ignore_permissions=True)
		)

		# Create temp merges CSV
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"merge_from",
					"merge_into",
					"evidence",
					"merge_considerations",
					"field_resolutions",
					"source_client_id",
				],
			)
			writer.writeheader()
			writer.writerow(
				{
					"merge_from": customer_from.name,
					"merge_into": customer_into.name,
					"evidence": "test",
					"merge_considerations": "",
					"field_resolutions": "",
					"source_client_id": "",
				}
			)
			temp_merges_path = f.name

		# Create temp deletes CSV
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(f, fieldnames=["customer", "reason", "decided_by", "date_decided"])
			writer.writeheader()
			writer.writerow(
				{
					"customer": customer_from.name,
					"reason": "test",
					"decided_by": "test",
					"date_decided": "2026-01-01",
				}
			)
			temp_deletes_path = f.name

		try:
			import ivm.customer_consolidation.apply as apply_module
			import ivm.customer_consolidation.decisions as decisions_module

			original_merges_path = decisions_module.CUSTOMER_MERGES_PATH
			original_deletes_path = decisions_module.CUSTOMERS_TO_DISABLE_PATH
			original_merges_loader = decisions_module.load_customer_merges
			original_deletes_loader = decisions_module.load_customers_to_disable

			def _patched_merges_load(path=None):
				return decisions_module._read_csv_rows(temp_merges_path)

			def _patched_deletes_load(path=None):
				return decisions_module._read_csv_rows(temp_deletes_path)

			decisions_module.CUSTOMER_MERGES_PATH = temp_merges_path
			decisions_module.CUSTOMERS_TO_DISABLE_PATH = temp_deletes_path
			decisions_module.load_customer_merges = _patched_merges_load
			decisions_module.load_customers_to_disable = _patched_deletes_load

			# Set hash to something different so it will try to apply
			original_hash_value = frappe.db.get_default(apply_module._DISABLE_APPLIED_HASH_KEY)
			frappe.db.set_default(apply_module._DISABLE_APPLIED_HASH_KEY, "not-the-real-hash")
			self.addCleanup(
				lambda: frappe.db.set_default(
					apply_module._DISABLE_APPLIED_HASH_KEY, original_hash_value or ""
				)
			)

			try:
				# This should NOT log an error because pending_merge is not a problem
				apply_customer_disables_on_migrate()
				# Hash SHOULD be saved because pending_merge is not a problem
				saved_hash = frappe.db.get_default(apply_module._DISABLE_APPLIED_HASH_KEY)
				self.assertNotEqual(saved_hash, "not-the-real-hash")
			finally:
				decisions_module.CUSTOMER_MERGES_PATH = original_merges_path
				decisions_module.CUSTOMERS_TO_DISABLE_PATH = original_deletes_path
				decisions_module.load_customer_merges = original_merges_loader
				decisions_module.load_customers_to_disable = original_deletes_loader
		finally:
			os.remove(temp_merges_path)
			os.remove(temp_deletes_path)


class TestRenameCustomersFromCsv(ERPNextTestSuite):
	"""rename_customers_from_csv: approved-only gate, per-row rename_status, review-site-gated CSV
	cross-reference rewrite. depends_on_merge is ignored.

	Every decision-file path is patched to a temp file (the functions read the module attributes
	live), so nothing here touches the real repo CSVs. The execute tests do a real rename, which
	commits, so the renamed Customer is deleted in addCleanup."""

	def _set_review_site(self, value):
		original = frappe.conf.get("customer_consolidation_review_site")
		if value is None:
			frappe.conf.pop("customer_consolidation_review_site", None)
		else:
			frappe.conf.customer_consolidation_review_site = value

		def _restore():
			if original is None:
				frappe.conf.pop("customer_consolidation_review_site", None)
			else:
				frappe.conf.customer_consolidation_review_site = original

		self.addCleanup(_restore)

	def _temp_csv(self, module_attr, header, rows):
		import ivm.customer_consolidation.decisions as decisions_module

		fd, temp_path = tempfile.mkstemp(suffix=".csv")
		with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
			writer = csv.writer(f)
			writer.writerow(header)
			writer.writerows(rows)

		patcher = patch.object(decisions_module, module_attr, temp_path)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(lambda: os.path.exists(temp_path) and os.remove(temp_path))
		return temp_path

	def _rename_rows(self, rows):
		return self._temp_csv(
			"CUSTOMER_RENAMES_PATH",
			[
				"current_name",
				"proposed_name",
				"confidence",
				"evidence",
				"status",
				"depends_on_merge",
				"notes",
			],
			rows,
		)

	def test_non_approved_row_is_skipped(self):
		current = _make_customer("RenameSkip").name
		self._rename_rows([[current, "Whatever Inc.", "low", "x", "needs_research", "", ""]])

		results = rename_customers_from_csv(execute=False)

		self.assertEqual(results[0]["action"], "skipped")

	def test_depends_on_merge_column_is_ignored(self):
		survivor = _make_customer("RenameDepIgnored").name
		self._rename_rows([[survivor, "Renamed Ignored", "high", "x", "approved", "true", ""]])

		results = rename_customers_from_csv(execute=False)

		self.assertEqual(results[0]["action"], "would_rename")
		self.assertNotIn("depends_on", results[0])

	def test_pending_when_current_exists_and_proposed_does_not(self):
		current = _make_customer("RenamePending").name
		self._rename_rows(
			[[current, f"Pending Target {frappe.generate_hash(length=8)}", "high", "x", "approved", "", ""]]
		)

		results = rename_customers_from_csv(execute=False)

		self.assertEqual(results[0]["action"], "would_rename")

	def test_already_applied_when_only_proposed_exists(self):
		proposed = _make_customer("RenameAlready").name
		self._rename_rows(
			[[f"GoneOld_{frappe.generate_hash(length=8)}", proposed, "high", "x", "approved", "", ""]]
		)

		results = rename_customers_from_csv(execute=False)

		self.assertEqual(results[0]["action"], "already_applied")

	def test_invalid_with_reason_when_neither_name_exists(self):
		missing = f"NoSuchCustomer_{frappe.generate_hash(length=8)}"
		self._rename_rows([[missing, "Also Missing Inc", "high", "x", "approved", "", ""]])

		results = rename_customers_from_csv(execute=False)

		self.assertEqual(results[0]["action"], "invalid")
		self.assertIn("neither", results[0]["reason"])

	def test_invalid_with_reason_when_both_names_exist(self):
		current = _make_customer("RenameBothA").name
		proposed = _make_customer("RenameBothB").name
		self._rename_rows([[current, proposed, "high", "x", "approved", "", ""]])

		results = rename_customers_from_csv(execute=False)

		self.assertEqual(results[0]["action"], "invalid")
		self.assertIn("both", results[0]["reason"])

	def test_execute_without_review_site_renames_db_only(self):
		self._set_review_site(None)
		old = _make_customer("RenameDbOnly").name
		new = f"RenamedDbOnly_{frappe.generate_hash(length=8)}"
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", new, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", new)
			else None
		)

		self._rename_rows([[old, new, "high", "x", "approved", "", ""]])
		merges = self._temp_csv(
			"CUSTOMER_MERGES_PATH",
			[
				"merge_from",
				"merge_into",
				"evidence",
				"merge_considerations",
				"field_resolutions",
				"source_client_id",
			],
			[["SomeDup", old, "x", "", "", ""]],
		)

		results = rename_customers_from_csv(execute=True)

		match = next(r for r in results if r["current_name"] == old)
		self.assertEqual(match["action"], "renamed")
		self.assertEqual(match["csv_rewrites"], {})
		self.assertTrue(frappe.db.exists("Customer", new))
		with open(merges, encoding="utf-8", newline="") as f:
			self.assertEqual(list(csv.reader(f))[1][1], old)

	def test_execute_rename_rewrites_references_in_all_four_decision_files(self):
		self._set_review_site(1)
		old = _make_customer("RenameOld").name
		new = f"RenamedNew_{frappe.generate_hash(length=8)}"
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", new, force=True, ignore_permissions=True)
			if frappe.db.exists("Customer", new)
			else None
		)

		self._rename_rows([[old, new, "high", "x", "approved", "", ""]])
		merges = self._temp_csv(
			"CUSTOMER_MERGES_PATH",
			[
				"merge_from",
				"merge_into",
				"evidence",
				"merge_considerations",
				"field_resolutions",
				"source_client_id",
			],
			[["SomeDup", old, "x", "", "", ""]],
		)
		assignments = self._temp_csv(
			"CLIENT_ASSIGNMENTS_PATH",
			["client_id", "customer", "evidence"],
			[["1234567", old, "x"]],
		)
		pairs = self._temp_csv(
			"CUSTOMER_DISTINCT_PAIRS_PATH",
			["customer_a", "customer_b", "client_id", "note"],
			[[old, "Other Co", "1234567", ""]],
		)
		reassignments = self._temp_csv(
			"RECORD_REASSIGNMENTS_PATH",
			["doctype", "name", "field", "from_customer", "to_customer", "evidence"],
			[["Issue", "ISS-X", "customer", "Elsewhere", old, "x"]],
		)

		results = rename_customers_from_csv(execute=True)

		match = next(r for r in results if r["current_name"] == old)
		self.assertEqual(match["action"], "renamed")
		# Counts are keyed by each (temp) file's basename, so assert one changed cell per file.
		self.assertEqual(len(match["csv_rewrites"]), 4)
		self.assertEqual(sorted(match["csv_rewrites"].values()), [1, 1, 1, 1])
		self.assertFalse(frappe.db.exists("Customer", old))
		self.assertTrue(frappe.db.exists("Customer", new))

		with open(merges, encoding="utf-8", newline="") as f:
			self.assertEqual(list(csv.reader(f))[1][1], new)
		with open(assignments, encoding="utf-8", newline="") as f:
			self.assertEqual(list(csv.reader(f))[1][1], new)
		with open(pairs, encoding="utf-8", newline="") as f:
			self.assertEqual(list(csv.reader(f))[1][0], new)
		with open(reassignments, encoding="utf-8", newline="") as f:
			self.assertEqual(list(csv.reader(f))[1][4], new)
