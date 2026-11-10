"""Tests for ivm.customer_consolidation.decisions"""

from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation.decisions import (
	apply_merge_map,
	compute_review_status,
	format_field_resolutions,
	parse_field_resolutions,
	resolve_merge_map,
	set_field_resolutions,
	upsert_client_assignment,
	upsert_client_merges,
	upsert_customer_to_create,
	upsert_distinct_pairs,
	validate_client_assignments,
	validate_customer_merges,
	validate_record_reassignments,
)
from ivm.customer_consolidation.dry_run import build_client_customer_matches


class TestResolveMergeMap(ERPNextTestSuite):
	"""resolve_merge_map"""

	def test_simple_merge(self):
		merge_map, cycles = resolve_merge_map([{"merge_from": "A", "merge_into": "B"}])
		self.assertEqual(merge_map, {"A": "B"})
		self.assertEqual(cycles, set())

	def test_chain_resolves_to_final_target(self):
		merges = [{"merge_from": "A", "merge_into": "B"}, {"merge_from": "B", "merge_into": "C"}]
		merge_map, cycles = resolve_merge_map(merges)
		self.assertEqual(merge_map, {"A": "C", "B": "C"})
		self.assertEqual(cycles, set())

	def test_cycle_detected(self):
		merges = [{"merge_from": "A", "merge_into": "B"}, {"merge_from": "B", "merge_into": "A"}]
		merge_map, cycles = resolve_merge_map(merges)
		self.assertEqual(merge_map, {})
		self.assertEqual(cycles, {"A", "B"})

	def test_duplicate_merge_from_uses_first_occurrence(self):
		merges = [
			{"merge_from": "A", "merge_into": "B"},
			{"merge_from": "A", "merge_into": "C"},
		]
		merge_map, _cycles = resolve_merge_map(merges)
		self.assertEqual(merge_map["A"], "B")


class TestValidateCustomerMerges(ERPNextTestSuite):
	"""validate_customer_merges"""

	def test_missing_merge_from_and_merge_into_customer(self):
		"""Both sides missing is a real problem, not an already-applied merge."""
		results = validate_customer_merges([{"merge_from": "Ghost", "merge_into": "AlsoGhost"}], set())
		self.assertIn("merge_from 'Ghost' does not exist", results[0]["errors"])
		self.assertEqual(results[0]["status"], "invalid")

	def test_missing_merge_into_customer(self):
		results = validate_customer_merges([{"merge_from": "Real", "merge_into": "Ghost"}], {"Real"})
		self.assertIn("merge_into 'Ghost' does not exist", results[0]["errors"])
		self.assertEqual(results[0]["status"], "invalid")

	def test_merge_from_gone_merge_into_exists_is_already_applied(self):
		"""merge_from no longer exists but merge_into does: the merge already happened. Not an
		error — the row becomes a permanent, idempotent record."""
		results = validate_customer_merges([{"merge_from": "Gone", "merge_into": "Real"}], {"Real"})
		self.assertEqual(results[0]["errors"], [])
		self.assertEqual(results[0]["status"], "already_applied")

	def test_pending_status_for_a_normal_valid_row(self):
		results = validate_customer_merges([{"merge_from": "A", "merge_into": "B"}], {"A", "B"})
		self.assertEqual(results[0]["status"], "pending")

	def test_self_merge(self):
		results = validate_customer_merges([{"merge_from": "A", "merge_into": "A"}], {"A"})
		self.assertIn("merge_from and merge_into are the same", results[0]["errors"])

	def test_duplicate_merge_from_flagged_on_second_row_only(self):
		merges = [
			{"merge_from": "A", "merge_into": "B"},
			{"merge_from": "A", "merge_into": "C"},
		]
		results = validate_customer_merges(merges, {"A", "B", "C"})
		self.assertEqual(results[0]["errors"], [])
		self.assertIn("merge_from 'A' is listed more than once", results[1]["errors"])

	def test_cycle_flagged(self):
		merges = [{"merge_from": "A", "merge_into": "B"}, {"merge_from": "B", "merge_into": "A"}]
		results = validate_customer_merges(merges, {"A", "B"})
		self.assertTrue(any("cycle" in e for e in results[0]["errors"]))
		self.assertTrue(any("cycle" in e for e in results[1]["errors"]))

	def test_valid_row_has_no_errors_and_correct_resolved_into(self):
		results = validate_customer_merges([{"merge_from": "A", "merge_into": "B"}], {"A", "B"})
		self.assertEqual(results[0]["errors"], [])
		self.assertEqual(results[0]["resolved_into"], "B")


class TestValidateClientAssignments(ERPNextTestSuite):
	"""validate_client_assignments"""

	def test_unknown_client_id(self):
		results = validate_client_assignments([{"client_id": "999", "customer": "A"}], {"A"}, {"100"}, {})
		self.assertIn("iCorp client 999 does not exist", results[0]["errors"])

	def test_unknown_customer(self):
		results = validate_client_assignments([{"client_id": "100", "customer": "Ghost"}], {"A"}, {"100"}, {})
		self.assertIn("customer 'Ghost' does not exist", results[0]["errors"])

	def test_duplicate_client_id(self):
		assignments = [
			{"client_id": "100", "customer": "A"},
			{"client_id": "100", "customer": "B"},
		]
		results = validate_client_assignments(assignments, {"A", "B"}, {"100"}, {})
		self.assertEqual(results[0]["errors"], [])
		self.assertIn("client_id 100 is listed more than once", results[1]["errors"])

	def test_customer_being_merged_away_resolves_with_no_error(self):
		results = validate_client_assignments(
			[{"client_id": "100", "customer": "A"}], {"A", "B"}, {"100"}, {"A": "B"}
		)
		self.assertEqual(results[0]["errors"], [])
		self.assertEqual(results[0]["resolved_customer"], "B")


class TestValidateRecordReassignments(ERPNextTestSuite):
	"""validate_record_reassignments"""

	def test_disallowed_doctype(self):
		results = validate_record_reassignments(
			[{"doctype": "Customer", "name": "X", "from_customer": "A", "to_customer": "B"}], {"A", "B"}, {}
		)
		self.assertIn("doctype 'Customer' is not allowed for record reassignment", results[0]["errors"])

	def test_wrong_field_for_doctype(self):
		results = validate_record_reassignments(
			[
				{
					"doctype": "Issue",
					"field": "account",
					"name": "ISS-1",
					"from_customer": "A",
					"to_customer": "B",
				}
			],
			{"A", "B"},
			{},
		)
		self.assertIn(
			"field 'account' does not match expected field 'customer' for Issue", results[0]["errors"]
		)

	def test_unknown_to_customer(self):
		results = validate_record_reassignments(
			[{"doctype": "Issue", "name": "ISS-1", "from_customer": "A", "to_customer": "Ghost"}], {"A"}, {}
		)
		self.assertIn("customer 'Ghost' does not exist", results[0]["errors"])

	def test_duplicate_record(self):
		rows = [
			{"doctype": "Issue", "name": "ISS-1", "from_customer": "A", "to_customer": "B"},
			{"doctype": "Issue", "name": "ISS-1", "from_customer": "A", "to_customer": "B"},
		]
		results = validate_record_reassignments(rows, {"A", "B"}, {})
		self.assertEqual(results[0]["errors"], [])
		self.assertIn("Issue 'ISS-1' is listed more than once", results[1]["errors"])

	def test_to_customer_being_merged_away_resolves_with_no_error(self):
		results = validate_record_reassignments(
			[{"doctype": "Issue", "name": "ISS-1", "from_customer": "A", "to_customer": "B"}],
			{"A", "B", "C"},
			{"B": "C"},
		)
		self.assertEqual(results[0]["errors"], [])
		self.assertEqual(results[0]["resolved_to_customer"], "C")

	def test_valid_row_resolves_field_from_doctype(self):
		results = validate_record_reassignments(
			[{"doctype": "Warehouse Request", "name": "WR-1", "from_customer": "A", "to_customer": "B"}],
			{"A", "B"},
			{},
		)
		self.assertEqual(results[0]["errors"], [])
		self.assertEqual(results[0]["resolved_field"], "account")


class TestApplyMergeMap(ERPNextTestSuite):
	"""apply_merge_map"""

	def test_remaps_project_customer_and_existing_ids_and_customer_name(self):
		project_rows = [{"name": "P1", "customer": "A", "client_id": "100"}]
		existing_ids = {"200": "A"}
		customers = [{"name": "A", "customer_name": "A"}, {"name": "B", "customer_name": "B"}]

		new_projects, new_existing_ids, new_customers = apply_merge_map(
			project_rows, existing_ids, customers, {"A": "B"}
		)

		self.assertEqual(new_projects[0]["customer"], "B")
		self.assertEqual(new_existing_ids["200"], "B")
		remapped = next(c for c in new_customers if c["customer_name"] == "A")
		self.assertEqual(remapped["name"], "B")

	def test_inputs_not_mutated(self):
		project_rows = [{"name": "P1", "customer": "A", "client_id": "100"}]
		existing_ids = {"200": "A"}
		customers = [{"name": "A", "customer_name": "A"}]

		apply_merge_map(project_rows, existing_ids, customers, {"A": "B"})

		self.assertEqual(project_rows[0]["customer"], "A")
		self.assertEqual(existing_ids["200"], "A")
		self.assertEqual(customers[0]["name"], "A")


class TestMergeTurnsConflictIntoConfirmed(ERPNextTestSuite):
	"""End-to-end (pure) check of the 3DS-style scenario: a conflict resolves to confirmed once the
	duplicate customers are merged."""

	def _scenario(self):
		icorp_clients = [
			{"id": 1268, "name": "3DS", "is_active": True, "partner_client_id": 0, "partner_client_name": ""}
		]
		project_rows = [{"name": "PROJ-0248", "customer": "3DS (Dassault)", "client_id": "1268"}]
		customers = [
			{"name": "3DS", "customer_name": "3DS"},
			{"name": "3DS (Dassault)", "customer_name": "3DS (Dassault)"},
		]
		return icorp_clients, project_rows, customers

	def test_conflict_before_merge(self):
		icorp_clients, project_rows, customers = self._scenario()
		matches = build_client_customer_matches(icorp_clients, project_rows, {}, customers)
		self.assertEqual(matches[0]["status"], "conflict")

	def test_confirmed_after_merge(self):
		icorp_clients, project_rows, customers = self._scenario()
		new_projects, new_existing_ids, new_customers = apply_merge_map(
			project_rows, {}, customers, {"3DS": "3DS (Dassault)"}
		)
		matches = build_client_customer_matches(icorp_clients, new_projects, new_existing_ids, new_customers)
		self.assertEqual(matches[0]["status"], "confirmed")
		self.assertEqual(matches[0]["proposed_customer"], "3DS (Dassault)")


class TestComputeReviewStatus(ERPNextTestSuite):
	"""compute_review_status"""

	def test_no_customer_no_proposal_no_rows_needs_match(self):
		self.assertEqual(compute_review_status("", "", [], set()), "Needs match")

	def test_proposal_only_no_rows_ready_to_accept(self):
		self.assertEqual(compute_review_status("", "Acme", [], {"Acme"}), "Ready to accept")

	def test_customer_set_no_rows_done(self):
		self.assertEqual(compute_review_status("Acme", "", [], {"Acme"}), "Done")

	def test_undecided_other_row_is_possible_duplicates(self):
		rows = [{"customer": "Acme", "role": ""}, {"customer": "Acme Co", "role": ""}]
		self.assertEqual(compute_review_status("", "Acme", rows, {"Acme", "Acme Co"}), "Possible duplicates")

	def test_duplicate_role_existing_customer_is_merge_pending(self):
		rows = [
			{"customer": "Acme", "role": "This client's Customer"},
			{"customer": "Acme Co", "role": "Duplicate - merge in"},
		]
		self.assertEqual(compute_review_status("Acme", "", rows, {"Acme", "Acme Co"}), "Merge pending")

	def test_duplicate_role_already_merged_customer_gone_is_done(self):
		rows = [
			{"customer": "Acme", "role": "This client's Customer"},
			{"customer": "Acme Co", "role": "Duplicate - merge in"},
		]
		self.assertEqual(compute_review_status("Acme", "", rows, {"Acme"}), "Done")

	def test_different_company_row_not_open(self):
		rows = [
			{"customer": "Acme", "role": "This client's Customer"},
			{"customer": "Acme Realty", "role": "Different company"},
		]
		self.assertEqual(compute_review_status("Acme", "", rows, {"Acme", "Acme Realty"}), "Done")

	def test_anchor_prefers_survivor_row_over_customer_field(self):
		rows = [{"customer": "New Co", "role": "This client's Customer"}]
		self.assertEqual(compute_review_status("Old Co", "", rows, {"New Co", "Old Co"}), "Done")


class TestUpsertClientAssignment(ERPNextTestSuite):
	def test_replaces_existing_row(self):
		rows = [{"client_id": "100", "customer": "Old", "evidence": ""}]
		result = upsert_client_assignment(rows, "100", "New", "evidence text")
		self.assertEqual(result, [{"client_id": "100", "customer": "New", "evidence": "evidence text"}])

	def test_removes_row_when_customer_blank(self):
		rows = [{"client_id": "100", "customer": "Old", "evidence": ""}]
		result = upsert_client_assignment(rows, "100", "", "")
		self.assertEqual(result, [])

	def test_other_client_rows_untouched(self):
		rows = [{"client_id": "999", "customer": "Other", "evidence": ""}]
		result = upsert_client_assignment(rows, "100", "New", "")
		self.assertEqual(len(result), 2)


class TestUpsertClientMerges(ERPNextTestSuite):
	def test_adds_new_desired_pair(self):
		result = upsert_client_merges([], "100", [("A", "B")], {"A", "B"})
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["merge_from"], "A")
		self.assertEqual(result[0]["merge_into"], "B")
		self.assertEqual(result[0]["source_client_id"], "100")

	def test_drops_no_longer_desired_row_from_same_client(self):
		rows = [{"merge_from": "A", "merge_into": "B", "source_client_id": "100"}]
		result = upsert_client_merges(rows, "100", [], {"A", "B"})
		self.assertEqual(result, [])

	def test_keeps_already_applied_row_from_same_client(self):
		rows = [{"merge_from": "A", "merge_into": "B", "source_client_id": "100"}]
		# "A" no longer exists -> already applied -> must survive even though not desired now
		result = upsert_client_merges(rows, "100", [], {"B"})
		self.assertEqual(len(result), 1)

	def test_keeps_rows_from_other_clients(self):
		rows = [{"merge_from": "A", "merge_into": "B", "source_client_id": "999"}]
		result = upsert_client_merges(rows, "100", [("C", "D")], {"A", "B", "C", "D"})
		self.assertEqual(len(result), 2)

	def test_conflicting_merge_into_raises(self):
		rows = [{"merge_from": "A", "merge_into": "B", "source_client_id": "999"}]
		with self.assertRaises(ValueError):
			upsert_client_merges(rows, "100", [("A", "C")], {"A", "B", "C"})

	def test_cycle_raises(self):
		rows = [{"merge_from": "A", "merge_into": "B", "source_client_id": "999"}]
		with self.assertRaises(ValueError):
			upsert_client_merges(rows, "100", [("B", "A")], {"A", "B"})


class TestUpsertDistinctPairs(ERPNextTestSuite):
	def test_adds_sorted_pair(self):
		result = upsert_distinct_pairs([], "100", "Zeta", ["Alpha"])
		self.assertEqual(
			result, [{"customer_a": "Alpha", "customer_b": "Zeta", "client_id": "100", "note": ""}]
		)

	def test_replaces_previous_rows_from_same_client(self):
		rows = [{"customer_a": "A", "customer_b": "B", "client_id": "100", "note": ""}]
		result = upsert_distinct_pairs(rows, "100", "C", ["D"])
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["customer_a"], "C")

	def test_other_client_rows_untouched(self):
		rows = [{"customer_a": "A", "customer_b": "B", "client_id": "999", "note": ""}]
		result = upsert_distinct_pairs(rows, "100", "C", ["D"])
		self.assertEqual(len(result), 2)

	def test_self_pair_skipped(self):
		result = upsert_distinct_pairs([], "100", "Same", ["Same"])
		self.assertEqual(result, [])


class TestParseFieldResolutionsJson(ERPNextTestSuite):
	"""parse_field_resolutions — JSON format"""

	def test_json_object_parsed(self):
		raw = '{"customer_type": "Company", "mobile_no": "123"}'
		self.assertEqual(parse_field_resolutions(raw), {"customer_type": "Company", "mobile_no": "123"})

	def test_json_value_with_semicolon_and_equals_preserved(self):
		raw = '{"corporate_hq": "123 Main St; Suite=5, Springfield"}'
		self.assertEqual(parse_field_resolutions(raw), {"corporate_hq": "123 Main St; Suite=5, Springfield"})

	def test_invalid_json_returns_empty(self):
		self.assertEqual(parse_field_resolutions("{not valid json"), {})

	def test_json_non_object_returns_empty(self):
		self.assertEqual(parse_field_resolutions("[1, 2, 3]"), {})

	def test_legacy_format_still_parses(self):
		self.assertEqual(
			parse_field_resolutions("field=value; field2=value2"),
			{"field": "value", "field2": "value2"},
		)

	def test_format_then_parse_round_trips(self):
		original = {"a": "1", "b": "two words", "c": "semi;colon=mix"}
		self.assertEqual(parse_field_resolutions(format_field_resolutions(original)), original)

	def test_format_empty_dict_returns_empty_string(self):
		self.assertEqual(format_field_resolutions({}), "")


class TestSetFieldResolutions(ERPNextTestSuite):
	"""set_field_resolutions"""

	def test_combines_with_existing_resolutions(self):
		rows = [
			{
				"merge_from": "A",
				"merge_into": "B",
				"field_resolutions": '{"customer_type": "Company"}',
			}
		]
		result = set_field_resolutions(rows, "A", {"mobile_no": "555"}, {"A", "B"})
		resolved = parse_field_resolutions(result[0]["field_resolutions"])
		self.assertEqual(resolved, {"customer_type": "Company", "mobile_no": "555"})

	def test_new_value_overwrites_existing_for_same_field(self):
		rows = [{"merge_from": "A", "merge_into": "B", "field_resolutions": '{"customer_type": "Company"}'}]
		result = set_field_resolutions(rows, "A", {"customer_type": "Integrator"}, {"A", "B"})
		resolved = parse_field_resolutions(result[0]["field_resolutions"])
		self.assertEqual(resolved, {"customer_type": "Integrator"})

	def test_already_applied_row_untouched(self):
		# "A" no longer exists -> already applied -> must not be modified
		rows = [{"merge_from": "A", "merge_into": "B", "field_resolutions": ""}]
		result = set_field_resolutions(rows, "A", {"customer_type": "Company"}, {"B"})
		self.assertEqual(result, rows)

	def test_other_rows_untouched(self):
		rows = [{"merge_from": "X", "merge_into": "Y", "field_resolutions": ""}]
		result = set_field_resolutions(rows, "A", {"customer_type": "Company"}, {"A", "X", "Y"})
		self.assertEqual(result, rows)


class TestUpsertCustomerToCreate(ERPNextTestSuite):
	def test_adds_new_row(self):
		result = upsert_customer_to_create(
			[],
			"Acme Inc",
			{
				"customer_type": "Company",
				"customer_group": "Individual",
				"territory": "All Territories",
				"source_client_id": "100",
				"note": "",
			},
		)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["customer_name"], "Acme Inc")
		self.assertEqual(result[0]["customer_type"], "Company")

	def test_replaces_existing_row_for_same_name(self):
		rows = [
			{
				"customer_name": "Acme Inc",
				"customer_type": "Company",
				"customer_group": "Old Group",
				"territory": "All Territories",
				"source_client_id": "100",
				"note": "",
			}
		]
		result = upsert_customer_to_create(
			rows,
			"Acme Inc",
			{
				"customer_type": "Company",
				"customer_group": "New Group",
				"territory": "All Territories",
				"source_client_id": "100",
				"note": "",
			},
		)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["customer_group"], "New Group")

	def test_other_rows_untouched(self):
		rows = [
			{
				"customer_name": "Other Co",
				"customer_type": "Company",
				"customer_group": "Individual",
				"territory": "All Territories",
				"source_client_id": "999",
				"note": "",
			}
		]
		upsert_customer_to_create(
			rows,
			"Acme Inc",
			{
				"customer_type": "Company",
				"customer_group": "Individual",
				"territory": "All Territories",
				"source_client_id": "100",
				"note": "",
			},
		)


class TestAppendCustomerMerges(ERPNextTestSuite):
	"""append_customer_merges"""

	def test_appends_new_row(self):
		from ivm.customer_consolidation.decisions import append_customer_merges

		rows = []
		new_rows = [{"merge_from": "A", "merge_into": "B", "evidence": "test"}]
		combined, skipped = append_customer_merges(rows, new_rows, {"A", "B"})
		self.assertEqual(len(combined), 1)
		self.assertEqual(combined[0]["merge_from"], "A")
		self.assertEqual(skipped, [])

	def test_skips_duplicate_pair(self):
		from ivm.customer_consolidation.decisions import append_customer_merges

		rows = [
			{
				"merge_from": "A",
				"merge_into": "B",
				"evidence": "old",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": "",
			}
		]
		new_rows = [{"merge_from": "A", "merge_into": "B", "evidence": "new"}]
		combined, skipped = append_customer_merges(rows, new_rows, {"A", "B"})
		self.assertEqual(len(combined), 1)
		self.assertEqual(len(skipped), 1)
		self.assertEqual(skipped[0]["reason"], "duplicate pair")

	def test_raises_on_conflicting_merge_into(self):
		from ivm.customer_consolidation.decisions import append_customer_merges

		rows = [
			{
				"merge_from": "A",
				"merge_into": "B",
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": "",
			}
		]
		new_rows = [{"merge_from": "A", "merge_into": "C", "evidence": ""}]
		with self.assertRaises(ValueError):
			append_customer_merges(rows, new_rows, {"A", "B", "C"})

	def test_raises_on_cycle(self):
		from ivm.customer_consolidation.decisions import append_customer_merges

		rows = [
			{
				"merge_from": "A",
				"merge_into": "B",
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": "",
			}
		]
		new_rows = [{"merge_from": "B", "merge_into": "A", "evidence": ""}]
		with self.assertRaises(ValueError):
			append_customer_merges(rows, new_rows, {"A", "B"})


class TestUpsertCustomersToDelete(ERPNextTestSuite):
	"""upsert_customers_to_disable"""

	def test_appends_new_customer(self):
		from ivm.customer_consolidation.decisions import upsert_customers_to_disable

		rows = []
		new_rows = [{"customer": "A", "reason": "orphan", "decided_by": "rule", "date_decided": "2024-01-01"}]
		result = upsert_customers_to_disable(rows, new_rows)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["customer"], "A")

	def test_skips_existing_customer(self):
		from ivm.customer_consolidation.decisions import upsert_customers_to_disable

		rows = [{"customer": "A", "reason": "old", "decided_by": "rule", "date_decided": "2024-01-01"}]
		new_rows = [{"customer": "A", "reason": "new", "decided_by": "rule", "date_decided": "2024-01-02"}]
		result = upsert_customers_to_disable(rows, new_rows)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["reason"], "old")

	def test_keeps_other_rows(self):
		from ivm.customer_consolidation.decisions import upsert_customers_to_disable

		rows = [{"customer": "X", "reason": "old", "decided_by": "rule", "date_decided": "2024-01-01"}]
		new_rows = [{"customer": "A", "reason": "new", "decided_by": "rule", "date_decided": "2024-01-02"}]
		result = upsert_customers_to_disable(rows, new_rows)
		self.assertEqual(len(result), 2)
		self.assertEqual(len(result), 2)


class TestRewriteCustomerReferences(ERPNextTestSuite):
	"""rewrite_customer_references: string repoint across the decision CSVs, plus self-merge drop.
	Decision-file paths are patched to temp files, so the real repo CSVs are never touched."""

	def _temp(self, module_attr, header, rows):
		import csv
		import os
		import tempfile
		from unittest.mock import patch

		import ivm.customer_consolidation.decisions as decisions_module

		fd, path = tempfile.mkstemp(suffix=".csv")
		with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
			w = csv.writer(f)
			w.writerow(header)
			w.writerows(rows)
		patcher = patch.object(decisions_module, module_attr, path)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
		return path

	def test_repoints_references_and_drops_self_merge_rows(self):
		import csv

		merges = self._temp(
			"CUSTOMER_MERGES_PATH",
			[
				"merge_from",
				"merge_into",
				"evidence",
				"merge_considerations",
				"field_resolutions",
				"source_client_id",
			],
			[
				["Dup", "OldName", "x", "", "", ""],
				["NewName", "OldName", "self-merge after rename", "", "", ""],
				["Keep", "Other", "x", "", "", ""],
			],
		)
		self._temp("CLIENT_ASSIGNMENTS_PATH", ["client_id", "customer", "evidence"], [["1", "OldName", "x"]])
		self._temp(
			"CUSTOMER_DISTINCT_PAIRS_PATH",
			["customer_a", "customer_b", "client_id", "note"],
			[["OldName", "Elsewhere", "1", ""]],
		)
		self._temp(
			"RECORD_REASSIGNMENTS_PATH",
			["doctype", "name", "field", "from_customer", "to_customer", "evidence"],
			[["Issue", "I-1", "customer", "Elsewhere", "OldName", "x"]],
		)

		from ivm.customer_consolidation.decisions import rewrite_customer_references

		counts = rewrite_customer_references("OldName", "NewName")

		self.assertEqual(
			sorted(counts.values()), [1, 1, 1, 2]
		)  # merges: 2 cells changed, 1 self-merge row dropped
		with open(merges, encoding="utf-8", newline="") as f:
			rows = list(csv.reader(f))
		self.assertEqual([r[:2] for r in rows[1:]], [["Dup", "NewName"], ["Keep", "Other"]])
