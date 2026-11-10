"""Tests for ivm.customer_consolidation.dry_run"""

import json
import os
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation.dry_run import (
	build_client_customer_matches,
	build_customer_coverage,
	build_customer_name_indexes,
	build_dry_run_report,
	fetch_icorp_clients,
	gather_customers,
	gather_existing_customer_icorp_ids,
	gather_hubspot_candidates,
	gather_project_rows,
	normalize_customer_name,
	parse_legacy_client_id,
	resolve_customer_for_name,
	run_icorp_migration_dry_run,
	summarize_client_matches,
	write_report_files,
)


class TestNormalizeCustomerName(ERPNextTestSuite):
	"""normalize_customer_name"""

	def test_acme_corp_inc(self):
		result = normalize_customer_name("Acme Corp Inc")
		self.assertEqual(result, "acme")

	def test_wesco_distribution_variants(self):
		result1 = normalize_customer_name("WESCO Distribution")
		result2 = normalize_customer_name("Wesco Distribution, Inc.")
		self.assertEqual(result1, result2)
		self.assertIn("wesco", result1)
		self.assertIn("distribution", result1)

	def test_none_input(self):
		self.assertEqual(normalize_customer_name(None), "")

	def test_empty_string(self):
		self.assertEqual(normalize_customer_name(""), "")

	def test_whitespace_only(self):
		self.assertEqual(normalize_customer_name("   "), "")

	def test_special_characters_stripped(self):
		result = normalize_customer_name("Acme & Co., Inc.")
		self.assertNotIn("&", result)
		self.assertNotIn(",", result)
		self.assertNotIn(".", result)
		self.assertNotIn("inc", result)

	def test_multiple_suffix_stripping(self):
		result = normalize_customer_name("Acme Corp Ltd Inc")
		self.assertNotIn("inc", result)
		self.assertNotIn("ltd", result)
		self.assertNotIn("corp", result)
		self.assertEqual(result, "acme")

	def test_non_suffix_token_preserved(self):
		result = normalize_customer_name("Acme Industries Inc")
		self.assertIn("industries", result)
		self.assertNotIn("inc", result)


class TestBuildCustomerNameIndexes(ERPNextTestSuite):
	"""build_customer_name_indexes"""

	def test_exact_index_single_customer(self):
		customers = [{"name": "CUST001", "customer_name": "Acme Inc"}]
		indexes = build_customer_name_indexes(customers)
		self.assertIn("acme inc", indexes["exact"])
		self.assertEqual(indexes["exact"]["acme inc"], ["CUST001"])

	def test_fuzzy_index_created(self):
		customers = [{"name": "CUST001", "customer_name": "Acme Industries, Inc."}]
		indexes = build_customer_name_indexes(customers)
		self.assertIn("acme industries", indexes["fuzzy"])
		self.assertEqual(indexes["fuzzy"]["acme industries"], ["CUST001"])

	def test_skip_empty_customer_name(self):
		customers = [
			{"name": "CUST001", "customer_name": "Acme Inc"},
			{"name": "CUST002", "customer_name": ""},
			{"name": "CUST003", "customer_name": None},
		]
		indexes = build_customer_name_indexes(customers)
		self.assertEqual(len(indexes["exact"]), 1)
		self.assertIn("acme inc", indexes["exact"])

	def test_multiple_customers_same_exact_name(self):
		customers = [
			{"name": "CUST001", "customer_name": "Acme Inc"},
			{"name": "CUST002", "customer_name": "Acme Inc"},
		]
		indexes = build_customer_name_indexes(customers)
		self.assertEqual(len(indexes["exact"]["acme inc"]), 2)
		self.assertIn("CUST001", indexes["exact"]["acme inc"])
		self.assertIn("CUST002", indexes["exact"]["acme inc"])


class TestResolveCustomerForName(ERPNextTestSuite):
	"""resolve_customer_for_name"""

	def test_exact_match_single_customer(self):
		customers = [{"name": "CUST001", "customer_name": "Acme Inc"}]
		indexes = build_customer_name_indexes(customers)
		result = resolve_customer_for_name("Acme Inc", indexes)
		self.assertEqual(result["customer"], "CUST001")
		self.assertEqual(result["confidence"], "exact")
		self.assertFalse(result["ambiguous"])

	def test_fuzzy_match_single_customer(self):
		customers = [{"name": "CUST001", "customer_name": "Acme Industries, Inc."}]
		indexes = build_customer_name_indexes(customers)
		result = resolve_customer_for_name("Acme Industries", indexes)
		self.assertEqual(result["customer"], "CUST001")
		self.assertEqual(result["confidence"], "fuzzy")
		self.assertFalse(result["ambiguous"])

	def test_ambiguous_exact_match(self):
		customers = [
			{"name": "CUST001", "customer_name": "Acme Inc"},
			{"name": "CUST002", "customer_name": "Acme Inc"},
		]
		indexes = build_customer_name_indexes(customers)
		result = resolve_customer_for_name("Acme Inc", indexes)
		self.assertIsNone(result["customer"])
		self.assertTrue(result["ambiguous"])

	def test_no_match(self):
		customers = [{"name": "CUST001", "customer_name": "Acme Inc"}]
		indexes = build_customer_name_indexes(customers)
		result = resolve_customer_for_name("Nonexistent Corp", indexes)
		self.assertIsNone(result["customer"])
		self.assertFalse(result["ambiguous"])
		self.assertIsNone(result["confidence"])

	def test_none_input(self):
		customers = [{"name": "CUST001", "customer_name": "Acme Inc"}]
		indexes = build_customer_name_indexes(customers)
		result = resolve_customer_for_name(None, indexes)
		self.assertIsNone(result["customer"])
		self.assertFalse(result["ambiguous"])


class TestBuildClientCustomerMatches(ERPNextTestSuite):
	"""build_client_customer_matches"""

	def test_project_only_evidence(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Client A",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		project_rows = [{"name": "P1", "customer": "CustA", "client_id": "100"}]
		matches = build_client_customer_matches(
			icorp_clients, project_rows, {}, [{"name": "CustA", "customer_name": "CustA"}]
		)
		self.assertEqual(matches[0]["status"], "project_only")
		self.assertEqual(matches[0]["proposed_customer"], "CustA")

	def test_existing_field_only_evidence(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Client A",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		matches = build_client_customer_matches(
			icorp_clients, [], {"100": "CustA"}, [{"name": "CustA", "customer_name": "CustA"}]
		)
		self.assertEqual(matches[0]["status"], "existing_field_only")
		self.assertEqual(matches[0]["proposed_customer"], "CustA")

	def test_name_exact_only_evidence(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Acme Industries",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		matches = build_client_customer_matches(
			icorp_clients, [], {}, [{"name": "CustA", "customer_name": "Acme Industries"}]
		)
		self.assertEqual(matches[0]["status"], "name_exact_only")
		self.assertEqual(matches[0]["proposed_customer"], "CustA")

	def test_name_fuzzy_only_evidence(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Acme Industries",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		matches = build_client_customer_matches(
			icorp_clients, [], {}, [{"name": "CustA", "customer_name": "Acme Industries Inc"}]
		)
		self.assertEqual(matches[0]["status"], "name_fuzzy_only")
		self.assertEqual(matches[0]["proposed_customer"], "CustA")

	def test_confirmed_multiple_sources(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Acme Inc",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		project_rows = [{"name": "P1", "customer": "CustA", "client_id": "100"}]
		matches = build_client_customer_matches(
			icorp_clients, project_rows, {}, [{"name": "CustA", "customer_name": "Acme Inc"}]
		)
		self.assertEqual(matches[0]["status"], "confirmed")
		self.assertEqual(matches[0]["proposed_customer"], "CustA")

	def test_conflict_with_project_evidence_still_leaves_proposed_customer_blank(self):
		"""Conflicts never get an automatic proposed_customer, even when one side has more
		project evidence than the other — tie-breaking a conflict is a guess, not a fact."""
		icorp_clients = [
			{
				"id": 100,
				"name": "Acme Inc",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		project_rows = [{"name": "P1", "customer": "CustA", "client_id": "100"}]
		customers = [
			{"name": "CustA", "customer_name": "CustA"},
			{"name": "CustB", "customer_name": "Acme Inc"},
		]
		matches = build_client_customer_matches(icorp_clients, project_rows, {}, customers)
		self.assertEqual(matches[0]["status"], "conflict")
		self.assertEqual(matches[0]["proposed_customer"], "")

	def test_conflict_no_project_evidence(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Acme Inc",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		customers = [
			{"name": "CustA", "customer_name": "CustA"},
			{"name": "CustB", "customer_name": "Acme Inc"},
		]
		matches = build_client_customer_matches(icorp_clients, [], {"100": "CustA"}, customers)
		self.assertEqual(matches[0]["status"], "conflict")
		self.assertEqual(matches[0]["proposed_customer"], "")

	def test_unmatched_no_evidence(self):
		icorp_clients = [
			{
				"id": 100,
				"name": "Unknown Client",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		matches = build_client_customer_matches(
			icorp_clients, [], {}, [{"name": "CustA", "customer_name": "Acme Inc"}]
		)
		self.assertEqual(matches[0]["status"], "unmatched")
		self.assertEqual(matches[0]["proposed_customer"], "")

	def test_assignment_override_wins(self):
		"""A manual assignment override forces status 'assigned_manually' regardless of other evidence."""
		icorp_clients = [
			{
				"id": 100,
				"name": "Acme Inc",
				"is_active": True,
				"partner_client_id": 0,
				"partner_client_name": "",
			}
		]
		project_rows = [{"name": "P1", "customer": "CustA", "client_id": "100"}]
		matches = build_client_customer_matches(
			icorp_clients,
			project_rows,
			{},
			[{"name": "CustA", "customer_name": "Acme Inc"}],
			assignment_overrides={"100": "CustOverride"},
		)
		self.assertEqual(matches[0]["status"], "assigned_manually")
		self.assertEqual(matches[0]["proposed_customer"], "CustOverride")

	def test_sort_order_active_status_name(self):
		icorp_clients = [
			{"id": 1, "name": "Zebra", "is_active": False, "partner_client_id": 0, "partner_client_name": ""},
			{"id": 2, "name": "Apple", "is_active": True, "partner_client_id": 0, "partner_client_name": ""},
			{"id": 3, "name": "Banana", "is_active": True, "partner_client_id": 0, "partner_client_name": ""},
		]
		matches = build_client_customer_matches(icorp_clients, [], {}, [])
		self.assertEqual([m["client_name"] for m in matches], ["Apple", "Banana", "Zebra"])


class TestSummarizeClientMatches(ERPNextTestSuite):
	"""summarize_client_matches"""

	def test_count_all_statuses(self):
		client_matches = [
			{"status": "confirmed"},
			{"status": "confirmed"},
			{"status": "project_only"},
			{"status": "existing_field_only"},
			{"status": "name_exact_only"},
			{"status": "name_fuzzy_only"},
			{"status": "conflict"},
			{"status": "assigned_manually"},
			{"status": "unmatched"},
		]
		summary = summarize_client_matches(client_matches)
		self.assertEqual(summary["total_clients"], 9)
		self.assertEqual(summary["confirmed"], 2)
		self.assertEqual(summary["assigned_manually"], 1)
		self.assertEqual(summary["unmatched"], 1)

	def test_all_keys_present_even_with_zero_counts(self):
		summary = summarize_client_matches([{"status": "confirmed"}, {"status": "confirmed"}])
		for key in (
			"confirmed",
			"project_only",
			"existing_field_only",
			"name_exact_only",
			"name_fuzzy_only",
			"conflict",
			"assigned_manually",
			"unmatched",
			"total_clients",
		):
			self.assertIn(key, summary)
		self.assertEqual(summary["project_only"], 0)
		self.assertEqual(summary["conflict"], 0)


class TestBuildCustomerCoverage(ERPNextTestSuite):
	"""build_customer_coverage"""

	def test_customer_in_confirmed_and_conflicting(self):
		client_matches = [
			{
				"client_id": "100",
				"status": "confirmed",
				"proposed_customer": "CustA",
				"_project_customer_counts": {"CustA": 2},
				"existing_field_customer": "",
				"_exact_name_customers": [],
				"_fuzzy_name_customers": [],
			},
			{
				"client_id": "200",
				"status": "conflict",
				"proposed_customer": "CustA",
				"_project_customer_counts": {"CustA": 1, "CustB": 1},
				"existing_field_customer": "",
				"_exact_name_customers": [],
				"_fuzzy_name_customers": [],
			},
		]
		coverage = build_customer_coverage(client_matches)
		cust_a = next(c for c in coverage if c["customer"] == "CustA")
		self.assertIn("100", cust_a["confirmed_client_ids"])
		self.assertIn("200", cust_a["conflicting_client_ids"])

	def test_customer_project_counts_sum(self):
		client_matches = [
			{
				"client_id": "100",
				"status": "project_only",
				"proposed_customer": "CustA",
				"_project_customer_counts": {"CustA": 3},
				"existing_field_customer": "",
				"_exact_name_customers": [],
				"_fuzzy_name_customers": [],
			},
			{
				"client_id": "200",
				"status": "project_only",
				"proposed_customer": "CustA",
				"_project_customer_counts": {"CustA": 2},
				"existing_field_customer": "",
				"_exact_name_customers": [],
				"_fuzzy_name_customers": [],
			},
		]
		coverage = build_customer_coverage(client_matches)
		self.assertEqual(coverage[0]["total_project_count"], 5)

	def test_customer_with_zero_evidence_not_in_output(self):
		client_matches = [
			{
				"client_id": "100",
				"status": "project_only",
				"proposed_customer": "CustA",
				"_project_customer_counts": {"CustA": 1},
				"existing_field_customer": "",
				"_exact_name_customers": [],
				"_fuzzy_name_customers": [],
			},
		]
		coverage = build_customer_coverage(client_matches)
		self.assertEqual(len(coverage), 1)
		self.assertEqual(coverage[0]["customer"], "CustA")


class TestGatherCustomers(ERPNextTestSuite):
	"""gather_customers"""

	def test_gather_customers_returns_list(self):
		for _ in range(2):
			frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": f"TestCust_{frappe.generate_hash(length=8)}",
					"customer_group": "_Test Customer Group",
					"territory": "All Territories",
				}
			).insert(ignore_permissions=True)

		result = gather_customers()
		self.assertIsInstance(result, list)
		self.assertGreater(len(result), 0)
		for customer in result:
			self.assertIn("name", customer)
			self.assertIn("customer_name", customer)


class TestParseLegacyClientId(ERPNextTestSuite):
	"""parse_legacy_client_id"""

	def test_empty_string(self):
		result = parse_legacy_client_id("")
		self.assertEqual(result["status"], "empty")

	def test_none(self):
		result = parse_legacy_client_id(None)
		self.assertEqual(result["status"], "empty")

	def test_whitespace_only(self):
		result = parse_legacy_client_id("   ")
		self.assertEqual(result["status"], "empty")

	def test_clean_numeric(self):
		result = parse_legacy_client_id("1334")
		self.assertEqual(result["status"], "clean")
		self.assertEqual(result["client_id"], "1334")

	def test_clean_with_parenthetical(self):
		result = parse_legacy_client_id("1334 (Master: 1011)")
		self.assertEqual(result["status"], "clean")
		self.assertEqual(result["client_id"], "1334")
		self.assertIn("1011", result["note"])

	def test_clean_with_parenthetical_no_space(self):
		result = parse_legacy_client_id("1334(Master: 1011)")
		self.assertEqual(result["status"], "clean")
		self.assertEqual(result["client_id"], "1334")

	def test_malformed_comma_separated(self):
		result = parse_legacy_client_id("1328, 1334")
		self.assertEqual(result["status"], "malformed")
		self.assertIn("comma", result["note"])

	def test_malformed_non_numeric(self):
		result = parse_legacy_client_id("abc")
		self.assertEqual(result["status"], "malformed")
		self.assertIn("unrecognized", result["note"])


class TestBuildDryRunReport(ERPNextTestSuite):
	"""build_dry_run_report"""

	def test_clean_id_single_customer_keep(self):
		icorp_clients = [
			{
				"id": 1334,
				"name": "Test Client",
				"is_active": True,
				"partner_client_id": 0,
				"is_partner_client": False,
			}
		]
		project_rows = [
			{"name": "P1", "customer": "Cust1", "client_id": "1334"},
			{"name": "P2", "customer": "Cust1", "client_id": "1334"},
		]
		report = build_dry_run_report(icorp_clients, project_rows, {})
		self.assertEqual(report["summary"]["projects_kept"], 2)
		for proj in report["per_project"]:
			self.assertEqual(proj["decision"], "keep")

	def test_clean_id_not_in_icorp_clear(self):
		icorp_clients = [
			{
				"id": 1000,
				"name": "Other",
				"is_active": True,
				"partner_client_id": 0,
				"is_partner_client": False,
			}
		]
		project_rows = [{"name": "P1", "customer": "Cust1", "client_id": "9999"}]
		report = build_dry_run_report(icorp_clients, project_rows, {})
		self.assertEqual(report["summary"]["projects_cleared_by_reason"].get("unknown_in_icorp"), 1)

	def test_clean_id_ambiguous_multiple_customers(self):
		icorp_clients = [
			{
				"id": 1334,
				"name": "Test",
				"is_active": True,
				"partner_client_id": 0,
				"is_partner_client": False,
			}
		]
		project_rows = [
			{"name": "P1", "customer": "CustA", "client_id": "1334"},
			{"name": "P2", "customer": "CustB", "client_id": "1334"},
		]
		report = build_dry_run_report(icorp_clients, project_rows, {})
		self.assertEqual(report["summary"]["projects_cleared_by_reason"].get("ambiguous"), 2)

	def test_malformed_value_clear(self):
		icorp_clients = [
			{
				"id": 1334,
				"name": "Test",
				"is_active": True,
				"partner_client_id": 0,
				"is_partner_client": False,
			}
		]
		project_rows = [{"name": "P1", "customer": "Cust1", "client_id": "1328, 1334"}]
		report = build_dry_run_report(icorp_clients, project_rows, {})
		self.assertEqual(report["summary"]["projects_cleared_by_reason"].get("malformed"), 1)

	def test_customer_mismatch_clear(self):
		icorp_clients = [
			{
				"id": 1334,
				"name": "Test",
				"is_active": True,
				"partner_client_id": 0,
				"is_partner_client": False,
			}
		]
		project_rows = [{"name": "P1", "customer": "CustA", "client_id": "1334"}]
		report = build_dry_run_report(icorp_clients, project_rows, {"1334": "CustA"})
		self.assertEqual(report["summary"]["projects_kept"], 1)

	def test_assignment_override_forces_assignable(self):
		"""A reviewed assignment override resolves an otherwise-unknown client id."""
		icorp_clients = [
			{
				"id": 1334,
				"name": "Test",
				"is_active": True,
				"partner_client_id": 0,
				"is_partner_client": False,
			}
		]
		project_rows = [{"name": "P1", "customer": "WrongCust", "client_id": "1334"}]
		report = build_dry_run_report(
			icorp_clients, project_rows, {}, assignment_overrides={"1334": "RightCust"}
		)
		self.assertEqual(report["per_project"][0]["decision"], "keep")
		self.assertEqual(report["per_project"][0]["assign_customer"], "RightCust")

	def test_summary_counts_add_up(self):
		icorp_clients = [
			{"id": 1, "name": "C1", "is_active": True, "partner_client_id": 0, "is_partner_client": False},
			{"id": 2, "name": "C2", "is_active": False, "partner_client_id": 1, "is_partner_client": True},
		]
		project_rows = [
			{"name": "P1", "customer": "Cust1", "client_id": "1"},
			{"name": "P2", "customer": "Cust2", "client_id": "1328, 1334"},
			{"name": "P3", "customer": "Cust3", "client_id": "9999"},
			{"name": "P4", "customer": "", "client_id": ""},
		]
		report = build_dry_run_report(icorp_clients, project_rows, {})
		summary = report["summary"]
		self.assertEqual(summary["total_projects_with_client_id"], 4)
		self.assertEqual(summary["projects_kept"], 1)
		self.assertEqual(summary["projects_unchanged"], 1)
		self.assertEqual(sum(summary["projects_cleared_by_reason"].values()), 2)
		self.assertEqual(summary["icorp_total_clients"], 2)
		self.assertEqual(summary["icorp_active_clients"], 1)


class TestGatherFunctions(ERPNextTestSuite):
	"""fetch_icorp_clients, gather_project_rows, gather_existing_customer_icorp_ids"""

	def test_fetch_icorp_clients_mocked(self):
		with patch("ivm.customer_consolidation.dry_run.icorp_api_get") as mock_get:
			mock_get.return_value = {
				"pagination": {"page": 1, "pageSize": 5000},
				"data": [
					{
						"id": 1,
						"name": "Client1",
						"is_active": True,
						"partner_client_id": 0,
						"is_partner_client": False,
					}
				],
			}
			result = fetch_icorp_clients()
			self.assertEqual(len(result), 1)
			mock_get.assert_called_once_with("Client?page=1&pageSize=5000")

	def test_gather_project_rows(self):
		cust_name = f"TestCust_{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": cust_name,
				"customer_group": "_Test Customer Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)

		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"TestProj_{frappe.generate_hash(length=8)}",
				"customer": cust_name,
				"client_id": "1234",
			}
		).insert(ignore_permissions=True)

		result = gather_project_rows()
		self.assertGreater(len(result), 0)
		for row in result:
			self.assertTrue(row.get("client_id"))

	def test_gather_existing_customer_icorp_ids(self):
		cust_name = f"TestCust_{frappe.generate_hash(length=8)}"
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": cust_name,
				"customer_group": "_Test Customer Group",
				"territory": "All Territories",
				"icorp_client_id": "5678",
			}
		).insert(ignore_permissions=True)

		result = gather_existing_customer_icorp_ids()
		self.assertEqual(result.get("5678"), cust_name)


class TestGatherHubspotCandidates(ERPNextTestSuite):
	"""gather_hubspot_candidates"""

	def test_deals_with_both_org_and_customer(self):
		org = frappe.get_doc(
			{
				"doctype": "CRM Organization",
				"organization_name": f"TestOrg_{frappe.generate_hash(length=8)}",
				"custom_hubspot_company_id": "hs123",
			}
		).insert(ignore_permissions=True)
		cust = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"TestCust_{frappe.generate_hash(length=8)}",
				"customer_group": "_Test Customer Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)
		deal = frappe.get_doc(
			{
				"doctype": "CRM Deal",
				"deal_name": f"TestDeal_{frappe.generate_hash(length=8)}",
				"organization": org.name,
				"custom_customer": cust.name,
			}
		).insert(ignore_permissions=True)

		result = gather_hubspot_candidates()
		found = next((d for d in result["deals_with_both"] if d["deal"] == deal.name), None)
		self.assertIsNotNone(found)
		self.assertEqual(found["customer"], cust.name)

	def test_name_matches_org_to_customer(self):
		org_name = f"MatchOrg_{frappe.generate_hash(length=8)}"
		org = frappe.get_doc(
			{
				"doctype": "CRM Organization",
				"organization_name": org_name,
				"custom_hubspot_company_id": "hs456",
			}
		).insert(ignore_permissions=True)
		cust = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": org_name,
				"customer_group": "_Test Customer Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)

		result = gather_hubspot_candidates()
		found = next((m for m in result["name_matches"] if m["organization"] == org.name), None)
		self.assertIsNotNone(found)
		self.assertEqual(found["matched_customer_name"], cust.name)

	def test_name_match_excluded_if_in_deal(self):
		org_name = f"ExcludedOrg_{frappe.generate_hash(length=8)}"
		org = frappe.get_doc(
			{
				"doctype": "CRM Organization",
				"organization_name": org_name,
				"custom_hubspot_company_id": "hs789",
			}
		).insert(ignore_permissions=True)
		cust = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": org_name,
				"customer_group": "_Test Customer Group",
				"territory": "All Territories",
			}
		).insert(ignore_permissions=True)
		deal = frappe.get_doc(
			{
				"doctype": "CRM Deal",
				"deal_name": f"TestDeal_{frappe.generate_hash(length=8)}",
				"organization": org.name,
				"custom_customer": cust.name,
			}
		).insert(ignore_permissions=True)

		result = gather_hubspot_candidates()
		self.assertTrue(any(d["deal"] == deal.name for d in result["deals_with_both"]))
		self.assertFalse(any(m["organization"] == org.name for m in result["name_matches"]))


class TestWriteReportFiles(ERPNextTestSuite):
	"""write_report_files"""

	def test_write_files_creates_all_seven(self):
		dry_run_report = {
			"per_project": [
				{
					"name": "P1",
					"customer": "C1",
					"legacy_client_id": "1234",
					"decision": "clear",
					"reason": "test reason",
				},
			],
			"per_id_classification": [],
			"summary": {
				"total_projects_with_client_id": 1,
				"projects_kept": 0,
				"projects_cleared_by_reason": {"test_reason": 1},
				"projects_unchanged": 0,
				"distinct_clean_ids": 0,
				"ids_assignable": 0,
				"ids_ambiguous": 0,
				"ids_unknown_in_icorp": 0,
				"ids_no_customer": 0,
				"existing_customer_icorp_id_count": 0,
				"icorp_total_clients": 0,
				"icorp_active_clients": 0,
				"icorp_clients_with_parent": 0,
				"icorp_clients_flagged_partner": 0,
			},
		}
		hubspot_report = {
			"deals_with_both": [
				{
					"deal": "D1",
					"organization": "O1",
					"organization_name": "Org1",
					"hubspot_company_id": "hs1",
					"customer": "C1",
				},
			],
			"name_matches": [],
		}
		client_matches = [
			{
				"client_id": "100",
				"client_name": "Test Client",
				"is_active": True,
				"sv_location_count_active": 1,
				"sv_machine_count_active": 5,
				"parent_client_id": "",
				"parent_client_name": "",
				"project_customers": "C1:1",
				"existing_field_customer": "",
				"exact_name_customers": "",
				"fuzzy_name_customers": "",
				"status": "project_only",
				"proposed_customer": "C1",
				"_project_customer_counts": {"C1": 1},
				"_exact_name_customers": [],
				"_fuzzy_name_customers": [],
			},
		]
		customer_coverage = [
			{
				"customer": "C1",
				"confirmed_client_ids": "",
				"single_source_client_ids": "100",
				"conflicting_client_ids": "",
				"total_project_count": 1,
			},
		]
		client_match_summary = {
			"total_clients": 1,
			"confirmed": 0,
			"project_only": 1,
			"existing_field_only": 0,
			"name_exact_only": 0,
			"name_fuzzy_only": 0,
			"conflict": 0,
			"assigned_manually": 0,
			"unmatched": 0,
		}
		merge_check_rows = [
			{
				"merge_from": "X",
				"merge_into": "Y",
				"resolved_into": "Y",
				"valid": "no",
				"ready_to_merge": "no",
				"validation_errors": ["merge_into 'Y' does not exist"],
				"linked_records_from": [],
				"linked_records_into": [],
				"fields_to_copy": [],
				"fields_in_conflict": [],
				"unresolved_field_conflicts": [],
				"contacts_from": [],
				"contacts_into": [],
				"possible_duplicate_contacts": [],
				"addresses_from": [],
				"addresses_into": [],
				"possible_duplicate_addresses": [],
				"icorp_clients_from": [],
				"icorp_clients_into": [],
				"evidence": "test",
				"merge_considerations": "",
			},
		]
		validated_assignments = [
			{
				"client_id": "999",
				"customer": "C1",
				"evidence": "test",
				"errors": [],
				"resolved_customer": "C1",
			},
		]
		client_match_summary_before_decisions = dict(client_match_summary)
		decisions_summary = {
			"merges_total": 1,
			"merges_valid": 0,
			"merges_invalid": 1,
			"assignments_total": 1,
			"assignments_valid": 1,
			"assignments_invalid": 0,
		}

		result = write_report_files(
			dry_run_report,
			hubspot_report,
			client_matches,
			customer_coverage,
			client_match_summary,
			merge_check_rows=merge_check_rows,
			validated_assignments=validated_assignments,
			client_match_summary_before_decisions=client_match_summary_before_decisions,
			decisions_summary=decisions_summary,
		)

		expected_keys = {
			"icorp_client_review",
			"hubspot_customer_review",
			"icorp_client_customer_matches",
			"customer_client_coverage",
			"planned_merges_check",
			"client_assignments_check",
			"icorp_migration_summary",
		}
		self.assertEqual(set(result.keys()), expected_keys)
		for path in result.values():
			self.assertTrue(os.path.exists(path))

		with open(result["planned_merges_check"]) as f:
			lines = f.readlines()
			self.assertIn("merge_from", lines[0])
			self.assertIn("X", lines[1])
			self.assertIn("no", lines[1])

		with open(result["client_assignments_check"]) as f:
			lines = f.readlines()
			self.assertIn("client_id", lines[0])
			self.assertIn("999", lines[1])

		with open(result["icorp_migration_summary"]) as f:
			summary = json.load(f)
			self.assertIn("client_match_summary_before_decisions", summary)
			self.assertIn("decisions_summary", summary)
			self.assertEqual(summary["decisions_summary"]["merges_invalid"], 1)

		for path in result.values():
			if os.path.exists(path):
				os.remove(path)


class TestRunIcorpMigrationDryRun(ERPNextTestSuite):
	"""run_icorp_migration_dry_run"""

	def test_run_without_write_files(self):
		with patch("ivm.customer_consolidation.dry_run.icorp_api_get") as mock_get:
			mock_get.return_value = {
				"pagination": {"page": 1},
				"data": [
					{
						"id": 1,
						"name": "C1",
						"is_active": True,
						"partner_client_id": 0,
						"is_partner_client": False,
					}
				],
			}
			result = run_icorp_migration_dry_run(write_files=False)

			self.assertIn("summary", result)
			self.assertIn("hubspot_summary", result)
			self.assertIn("client_match_summary", result)
			self.assertIn("client_match_summary_before_decisions", result)
			self.assertIn("decisions_summary", result)
			self.assertIn("files", result)
			self.assertEqual(result["files"], {})
			self.assertIn("total_clients", result["client_match_summary"])

	def test_run_with_write_files_string_true(self):
		with patch("ivm.customer_consolidation.dry_run.icorp_api_get") as mock_get:
			mock_get.return_value = {
				"pagination": {"page": 1},
				"data": [
					{
						"id": 1,
						"name": "C1",
						"is_active": True,
						"partner_client_id": 0,
						"is_partner_client": False,
					}
				],
			}
			result = run_icorp_migration_dry_run(write_files="true")

			self.assertIn("summary", result)
			self.assertGreater(len(result["files"]), 0)
			self.assertIn("decisions_summary", result)

			for path in result["files"].values():
				if os.path.exists(path):
					os.remove(path)
