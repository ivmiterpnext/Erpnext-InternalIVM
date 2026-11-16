"""Tests for ivm.customer_consolidation.orphan_customers"""

import csv
import os
import tempfile
from unittest import mock

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation import decisions
from ivm.customer_consolidation.orphan_customers import (
	SUGGESTION_LINK_FIELDS,
	_child_table_summary,
	_non_default_fields,
	count_links_for_all_customers,
	find_orphan_customers,
	report_low_link_customers,
	report_orphan_customers,
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


class TestFindOrphanCustomers(ERPNextTestSuite):
	"""find_orphan_customers"""

	def test_customer_with_no_links_is_orphan(self):
		orphan = _make_customer("OrphanNoLinks")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", orphan.name, force=True, ignore_permissions=True)
		)

		orphans = find_orphan_customers()
		self.assertIn(orphan.name, orphans)

	def test_customer_with_project_link_is_not_orphan(self):
		customer = _make_customer("LinkedViaProject")
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

		orphans = find_orphan_customers()
		self.assertNotIn(customer.name, orphans)

	def test_customer_with_contact_dynamic_link_is_not_orphan(self):
		customer = _make_customer("LinkedViaContact")
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Test",
				"last_name": "Contact",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Dynamic Link",
				"parenttype": "Contact",
				"parent": contact.name,
				"link_doctype": "Customer",
				"link_name": customer.name,
			}
		).db_insert()
		self.addCleanup(
			lambda: frappe.delete_doc("Contact", contact.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		orphans = find_orphan_customers()
		self.assertNotIn(customer.name, orphans)

	def test_customer_in_merge_from_is_excluded(self):
		customer = _make_customer("ExcludedMergeFrom")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create temp CSV with this customer as merge_from
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
					"merge_from": customer.name,
					"merge_into": "SomeOther",
					"evidence": "",
					"merge_considerations": "",
					"field_resolutions": "",
					"source_client_id": "",
				}
			)
			temp_path = f.name

		try:
			merges = decisions.load_customer_merges(path=temp_path)
			self.assertTrue(any(r["merge_from"] == customer.name for r in merges))

			# Patch load_customer_merges to use our temp file
			import ivm.customer_consolidation.decisions as decisions_module

			original = decisions_module.load_customer_merges

			def _patched_load(path=None):
				return decisions_module._read_csv_rows(temp_path)

			decisions_module.load_customer_merges = _patched_load
			self.addCleanup(lambda: setattr(decisions_module, "load_customer_merges", original))

			orphans = find_orphan_customers()
			self.assertNotIn(customer.name, orphans)
		finally:
			os.remove(temp_path)


class TestNonDefaultFields(ERPNextTestSuite):
	"""_non_default_fields"""

	def test_minimal_fields_returns_mostly_empty(self):
		# Create a customer with minimal fields (just customer_name, which is required)
		# Frappe auto-fills some fields like customer_type, language, etc., but those are system defaults
		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": f"Minimal_{frappe.generate_hash(length=8)}",
			}
		).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("Customer", doc.name, force=True, ignore_permissions=True))

		result = _non_default_fields(doc.name)
		# Result should not include website, fax, phone, etc. (the fields we care about for reporting)
		# It may include auto-filled system fields like customer_type, language, etc.
		self.assertNotIn("website", result)
		self.assertNotIn("fax", result)
		self.assertNotIn("phone", result)

	def test_non_default_field_included_in_result(self):
		customer = _make_customer("WithWebsite", website="https://example.com")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		result = _non_default_fields(customer.name)
		self.assertIn("website", result)
		self.assertIn("https://example.com", result)

	def test_customer_name_field_skipped(self):
		customer = _make_customer("SkipCustomerName")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		result = _non_default_fields(customer.name)
		self.assertNotIn("customer_name", result)


class TestChildTableSummary(ERPNextTestSuite):
	"""_child_table_summary"""

	def test_no_child_rows_returns_empty_string(self):
		customer = _make_customer("NoChildRows")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		result = _child_table_summary(customer.name)
		self.assertEqual(result, "")

	def test_child_table_rows_counted(self):
		customer = _make_customer("WithAccounts")
		company = frappe.db.get_value("Company", {}, "name")
		customer.append("accounts", {"company": company, "account": None})
		customer.save(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		result = _child_table_summary(customer.name)
		self.assertIn("accounts:1", result)


class TestCountLinksForAllCustomers(ERPNextTestSuite):
	"""count_links_for_all_customers and parity with count_linked_records"""

	def test_bulk_count_matches_per_customer_count_single_project(self):
		"""Parity test: bulk count for a customer with one Project link matches per-customer count."""
		customer = _make_customer("BulkCountProject")
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

		# Get bulk counts
		bulk_counts = count_links_for_all_customers()
		bulk_for_customer = bulk_counts.get(customer.name, {})

		# Get per-customer counts
		link_fields = __import__(
			"ivm.customer_consolidation.merge_analysis", fromlist=["get_customer_link_fields"]
		).get_customer_link_fields()
		per_customer_list = __import__(
			"ivm.customer_consolidation.merge_analysis", fromlist=["count_linked_records"]
		).count_linked_records(customer.name, link_fields)

		# Convert per-customer list to dict for comparison
		per_customer_dict = {}
		for entry in per_customer_list:
			label, count_str = entry.rsplit(":", 1)
			per_customer_dict[label] = int(count_str)

		# Should match
		self.assertEqual(
			bulk_for_customer,
			per_customer_dict,
			f"Bulk: {bulk_for_customer}, Per-customer: {per_customer_dict}",
		)

	def test_bulk_count_matches_per_customer_count_multiple_links(self):
		"""Parity test: bulk count for a customer with multiple link types matches per-customer count."""
		customer = _make_customer("BulkCountMultiple")

		# Create a Project link
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_type": "Internal",
				"project_name": f"TestProj_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)

		# Create two Issue links
		issue1 = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": f"Issue1_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)

		issue2 = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": f"Issue2_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)

		self.addCleanup(
			lambda: frappe.delete_doc("Project", project.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(lambda: frappe.delete_doc("Issue", issue1.name, force=True, ignore_permissions=True))
		self.addCleanup(lambda: frappe.delete_doc("Issue", issue2.name, force=True, ignore_permissions=True))
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Get bulk counts
		bulk_counts = count_links_for_all_customers()
		bulk_for_customer = bulk_counts.get(customer.name, {})

		# Get per-customer counts
		link_fields = __import__(
			"ivm.customer_consolidation.merge_analysis", fromlist=["get_customer_link_fields"]
		).get_customer_link_fields()
		per_customer_list = __import__(
			"ivm.customer_consolidation.merge_analysis", fromlist=["count_linked_records"]
		).count_linked_records(customer.name, link_fields)

		# Convert per-customer list to dict for comparison
		per_customer_dict = {}
		for entry in per_customer_list:
			label, count_str = entry.rsplit(":", 1)
			per_customer_dict[label] = int(count_str)

		# Should match
		self.assertEqual(
			bulk_for_customer,
			per_customer_dict,
			f"Bulk: {bulk_for_customer}, Per-customer: {per_customer_dict}",
		)

	def test_bulk_count_includes_dynamic_link(self):
		"""Parity test: bulk count includes Dynamic Link entries."""
		customer = _make_customer("BulkCountDynamic")
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Test",
				"last_name": "Contact",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Dynamic Link",
				"parenttype": "Contact",
				"parent": contact.name,
				"link_doctype": "Customer",
				"link_name": customer.name,
			}
		).db_insert()
		self.addCleanup(
			lambda: frappe.delete_doc("Contact", contact.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Get bulk counts
		bulk_counts = count_links_for_all_customers()
		bulk_for_customer = bulk_counts.get(customer.name, {})

		# Get per-customer counts
		link_fields = __import__(
			"ivm.customer_consolidation.merge_analysis", fromlist=["get_customer_link_fields"]
		).get_customer_link_fields()
		per_customer_list = __import__(
			"ivm.customer_consolidation.merge_analysis", fromlist=["count_linked_records"]
		).count_linked_records(customer.name, link_fields)

		# Convert per-customer list to dict for comparison
		per_customer_dict = {}
		for entry in per_customer_list:
			label, count_str = entry.rsplit(":", 1)
			per_customer_dict[label] = int(count_str)

		# Should match
		self.assertEqual(
			bulk_for_customer,
			per_customer_dict,
			f"Bulk: {bulk_for_customer}, Per-customer: {per_customer_dict}",
		)


class TestSuggestionLinks(ERPNextTestSuite):
	"""Suggestion links don't count toward total but appear in breakdown"""

	def test_suggestion_link_excluded_from_total(self):
		"""A customer with only a suggestion link (proposed_customer) should be an orphan."""
		customer = _make_customer("SuggestionLinkOnly")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create an iCorp Client Link with proposed_customer pointing to this customer
		# (no other links)
		icorp_link = frappe.get_doc(
			{
				"doctype": "iCorp Client Link",
				"icorp_client_id": frappe.generate_hash(length=12),
				"proposed_customer": customer.name,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", icorp_link.name, force=True, ignore_permissions=True
			)
		)

		# Should be in orphans (suggestion link doesn't count)
		orphans = find_orphan_customers()
		self.assertIn(customer.name, orphans)

	def test_suggestion_link_appears_in_breakdown(self):
		"""Suggestion link should appear in link_breakdown with (suggestion) marker."""
		customer = _make_customer("SuggestionInBreakdown")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create an iCorp Client Link with proposed_customer
		icorp_link = frappe.get_doc(
			{
				"doctype": "iCorp Client Link",
				"icorp_client_id": frappe.generate_hash(length=12),
				"proposed_customer": customer.name,
			}
		).insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc(
				"iCorp Client Link", icorp_link.name, force=True, ignore_permissions=True
			)
		)

		# Generate report
		path = report_low_link_customers(max_links=0)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and find the row
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 1)
		breakdown = rows[0]["link_breakdown"]
		self.assertIn("proposed_customer", breakdown)
		self.assertIn("(suggestion)", breakdown)


class TestReportLowLinkCustomers(ERPNextTestSuite):
	"""report_low_link_customers with various thresholds"""

	def test_threshold_boundary_included(self):
		"""A customer with exactly max_links real links is included."""
		customer = _make_customer("ThresholdBoundary")

		# Create exactly 2 Issues (2 real links)
		issue1 = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": f"Issue1_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)

		issue2 = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": f"Issue2_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)

		self.addCleanup(lambda: frappe.delete_doc("Issue", issue1.name, force=True, ignore_permissions=True))
		self.addCleanup(lambda: frappe.delete_doc("Issue", issue2.name, force=True, ignore_permissions=True))
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# With max_links=2, should be included
		path = report_low_link_customers(max_links=2)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 1)
		self.assertEqual(int(rows[0]["total_links"]), 2)

	def test_threshold_boundary_excluded(self):
		"""A customer with max_links + 1 real links is excluded."""
		customer = _make_customer("ThresholdExcluded")

		# Create 3 Issues (3 real links)
		for i in range(3):
			issue = frappe.get_doc(
				{
					"doctype": "Issue",
					"subject": f"Issue{i}_{frappe.generate_hash(length=8)}",
					"customer": customer.name,
				}
			).insert(ignore_permissions=True)
			self.addCleanup(
				lambda issue=issue: frappe.delete_doc(
					"Issue", issue.name, force=True, ignore_permissions=True
				)
			)

		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# With max_links=2, should be excluded
		path = report_low_link_customers(max_links=2)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 0)

	def test_sort_order_by_total_links(self):
		"""Customers are sorted by total_links ascending, then by name."""
		cust0 = _make_customer("SortOrder0")
		cust2 = _make_customer("SortOrder2")
		cust5 = _make_customer("SortOrder5")

		# cust2: 2 Issues
		for i in range(2):
			issue = frappe.get_doc(
				{
					"doctype": "Issue",
					"subject": f"Issue{i}_{frappe.generate_hash(length=8)}",
					"customer": cust2.name,
				}
			).insert(ignore_permissions=True)
			self.addCleanup(
				lambda issue=issue: frappe.delete_doc(
					"Issue", issue.name, force=True, ignore_permissions=True
				)
			)

		# cust5: 5 Issues
		for i in range(5):
			issue = frappe.get_doc(
				{
					"doctype": "Issue",
					"subject": f"Issue{i}_{frappe.generate_hash(length=8)}",
					"customer": cust5.name,
				}
			).insert(ignore_permissions=True)
			self.addCleanup(
				lambda issue=issue: frappe.delete_doc(
					"Issue", issue.name, force=True, ignore_permissions=True
				)
			)

		self.addCleanup(
			lambda: frappe.delete_doc("Customer", cust0.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", cust2.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", cust5.name, force=True, ignore_permissions=True)
		)

		path = report_low_link_customers(max_links=10)
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] in [cust0.name, cust2.name, cust5.name]]

		# Should be in order: 0, 2, 5
		self.assertEqual(len(rows), 3)
		self.assertEqual(rows[0]["name"], cust0.name)
		self.assertEqual(rows[1]["name"], cust2.name)
		self.assertEqual(rows[2]["name"], cust5.name)


class TestReportOrphanCustomers(ERPNextTestSuite):
	"""report_orphan_customers"""

	def test_report_writes_csv_with_correct_header(self):
		orphan = _make_customer("ReportOrphan")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", orphan.name, force=True, ignore_permissions=True)
		)

		path = report_orphan_customers()
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		self.assertTrue(os.path.exists(path))
		with open(path) as f:
			reader = csv.DictReader(f)
			header = reader.fieldnames
			self.assertEqual(
				header,
				[
					"name",
					"customer_name",
					"creation",
					"disabled",
					"total_links",
					"link_breakdown",
					"non_default_fields",
					"child_table_rows",
				],
			)

	def test_report_includes_orphan_row(self):
		orphan = _make_customer("ReportIncludeOrphan")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", orphan.name, force=True, ignore_permissions=True)
		)

		path = report_orphan_customers()
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		with open(path) as f:
			reader = csv.DictReader(f)
			rows = list(reader)
			orphan_rows = [r for r in rows if r["name"] == orphan.name]
			self.assertEqual(len(orphan_rows), 1)
			self.assertEqual(orphan_rows[0]["name"], orphan.name)

	def test_report_incremental_durability_on_exception(self):
		"""Verify that if report_low_link_customers() raises partway through,
		the CSV file still exists on disk with the header and at least one row written
		before the exception, proving incremental streaming works."""
		orphan1 = _make_customer("IncrementalDurability1")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", orphan1.name, force=True, ignore_permissions=True)
		)

		# Monkeypatch _child_table_summary to raise on the 2nd call (after first orphan is written)
		from ivm.customer_consolidation import orphan_customers as oc_module

		original_child_table_summary = oc_module._child_table_summary
		call_count = [0]

		def _patched_child_table_summary(customer):
			call_count[0] += 1
			if call_count[0] == 2:
				raise RuntimeError("Simulated interruption after first orphan")
			return original_child_table_summary(customer)

		oc_module._child_table_summary = _patched_child_table_summary
		self.addCleanup(lambda: setattr(oc_module, "_child_table_summary", original_child_table_summary))

		# Delete any existing report file for today to start fresh
		site_path = frappe.get_site_path("private", "files")
		existing_path = os.path.join(site_path, f"low_link_customers_report_{frappe.utils.nowdate()}.csv")
		if os.path.exists(existing_path):
			os.remove(existing_path)

		# Call report_low_link_customers() and expect it to raise
		with self.assertRaises(RuntimeError) as cm:
			report_low_link_customers(max_links=0)
		self.assertIn("Simulated interruption", str(cm.exception))

		# Verify file exists and contains the header + at least one row
		self.assertTrue(os.path.exists(existing_path), f"CSV file should exist at {existing_path}")
		self.addCleanup(lambda: os.remove(existing_path) if os.path.exists(existing_path) else None)

		with open(existing_path) as f:
			reader = csv.DictReader(f)
			rows = list(reader)

		# Should have at least 1 row (the first orphan encountered, before the exception)
		# This proves that incremental streaming works: the file was flushed to disk
		# before the exception was raised
		self.assertGreaterEqual(len(rows), 1, f"Expected at least 1 row in CSV, got {len(rows)}")
		# Verify the CSV has the correct header structure
		self.assertEqual(
			reader.fieldnames,
			[
				"name",
				"customer_name",
				"creation",
				"disabled",
				"total_links",
				"link_breakdown",
				"non_default_fields",
				"child_table_rows",
			],
		)

	def test_report_progress_print_with_few_customers(self):
		"""Verify that progress printing (every 100 customers) doesn't error
		when there are fewer than 100 customers total."""
		orphan = _make_customer("ProgressPrintFew")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", orphan.name, force=True, ignore_permissions=True)
		)

		# Should complete normally without errors, even though checked % 100 == 0 never fires
		path = report_orphan_customers()
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		self.assertTrue(os.path.exists(path))
		with open(path) as f:
			reader = csv.DictReader(f)
			list(reader)
			# Should have at least the orphan we created


class TestOperationalLinkTotal(ERPNextTestSuite):
	"""operational_link_total"""

	def test_suggestion_only_returns_zero(self):
		from ivm.customer_consolidation.orphan_customers import operational_link_total

		link_counts = {"iCorp Client Link.proposed_customer": 3}
		self.assertEqual(operational_link_total(link_counts), 0)

	def test_contact_address_only_returns_zero(self):
		from ivm.customer_consolidation.orphan_customers import operational_link_total

		link_counts = {"Contact (dynamic link)": 2, "Address (dynamic link)": 1}
		self.assertEqual(operational_link_total(link_counts), 0)

	def test_issue_customer_counted(self):
		from ivm.customer_consolidation.orphan_customers import operational_link_total

		link_counts = {"Issue.customer": 3}
		self.assertEqual(operational_link_total(link_counts), 3)

	def test_mixed_suggestion_and_operational(self):
		from ivm.customer_consolidation.orphan_customers import operational_link_total

		link_counts = {
			"Issue.customer": 5,
			"iCorp Client Link.proposed_customer": 2,
			"Contact (dynamic link)": 1,
		}
		self.assertEqual(operational_link_total(link_counts), 5)


class TestClassifyCustomer(ERPNextTestSuite):
	"""classify_customer"""

	def test_operational_link_present_returns_keep(self):
		import datetime

		from ivm.customer_consolidation.orphan_customers import classify_customer

		link_counts = {"Issue.customer": 3}
		action, reason = classify_customer(link_counts, None, "2024-01-01", datetime.date(2024, 1, 1))
		self.assertEqual(action, "keep")
		self.assertIn("Issue.customer:3", reason)

	def test_closed_won_opportunity_returns_review(self):
		import datetime

		from ivm.customer_consolidation.orphan_customers import classify_customer

		link_counts = {}
		opp_summary = {"stages": {"Closed Won": 1}, "last_txn": None, "has_won": True}
		action, reason = classify_customer(link_counts, opp_summary, "2023-01-01", datetime.date(2024, 1, 1))
		self.assertEqual(action, "review")
		self.assertIn("Closed Won", reason)

	def test_recent_creation_returns_review(self):
		import datetime

		from ivm.customer_consolidation.orphan_customers import classify_customer

		link_counts = {}
		cutoff = datetime.date(2024, 1, 1)
		action, reason = classify_customer(link_counts, None, "2024-01-15", cutoff)
		self.assertEqual(action, "review")
		self.assertIn("created on or after", reason)

	def test_recent_opportunity_transaction_returns_review(self):
		import datetime

		from ivm.customer_consolidation.orphan_customers import classify_customer

		link_counts = {}
		cutoff = datetime.date(2024, 1, 1)
		opp_summary = {"stages": {"Prospecting": 1}, "last_txn": "2024-01-15", "has_won": False}
		action, reason = classify_customer(link_counts, opp_summary, "2023-01-01", cutoff)
		self.assertEqual(action, "review")
		self.assertIn("transaction_date", reason)

	def test_no_links_old_creation_returns_disable(self):
		import datetime

		from ivm.customer_consolidation.orphan_customers import classify_customer

		link_counts = {}
		cutoff = datetime.date(2024, 1, 1)
		action, reason = classify_customer(link_counts, None, "2023-01-01", cutoff)
		self.assertEqual(action, "disable")
		self.assertIn("no operational links", reason)


class TestNormalizeForDedupe(ERPNextTestSuite):
	"""normalize_for_dedupe"""

	def test_strips_tv_suffix(self):
		from ivm.customer_consolidation.orphan_customers import normalize_for_dedupe

		result = normalize_for_dedupe("Foo (TV)")
		self.assertEqual(result, "foo")

	def test_strips_tv_with_whitespace(self):
		from ivm.customer_consolidation.orphan_customers import normalize_for_dedupe

		result = normalize_for_dedupe("Foo ( TV )")
		self.assertEqual(result, "foo")

	def test_strips_trailing_digits(self):
		from ivm.customer_consolidation.orphan_customers import normalize_for_dedupe

		result = normalize_for_dedupe("AES - 1")
		self.assertEqual(result, "aes")

	def test_empty_name_returns_empty(self):
		from ivm.customer_consolidation.orphan_customers import normalize_for_dedupe

		result = normalize_for_dedupe(None)
		self.assertEqual(result, "")
		result = normalize_for_dedupe("")
		self.assertEqual(result, "")


class TestBuildDuplicateGroups(ERPNextTestSuite):
	"""build_duplicate_groups"""

	def test_single_customer_not_grouped(self):
		from ivm.customer_consolidation.orphan_customers import build_duplicate_groups

		customers = [{"name": "A", "customer_name": "Foo Inc", "creation": "2024-01-01"}]
		classifications = {"A": ("keep", "has links")}
		link_totals = {"A": 5}
		groups = build_duplicate_groups(customers, classifications, link_totals, set())
		self.assertEqual(groups, {})

	def test_two_customers_same_normalized_name_grouped(self):
		from ivm.customer_consolidation.orphan_customers import build_duplicate_groups

		customers = [
			{"name": "A", "customer_name": "Foo Inc", "creation": "2024-01-01"},
			{"name": "B", "customer_name": "Foo Inc", "creation": "2024-01-02"},
		]
		classifications = {"A": ("keep", "has links"), "B": ("disable", "no links")}
		link_totals = {"A": 5, "B": 0}
		groups = build_duplicate_groups(customers, classifications, link_totals, set())
		self.assertEqual(len(groups), 2)
		self.assertEqual(groups["A"]["survivor"], "A")
		self.assertTrue(groups["A"]["is_survivor"])
		self.assertEqual(groups["B"]["survivor"], "A")
		self.assertFalse(groups["B"]["is_survivor"])

	def test_non_tv_wins_tie_over_tv(self):
		from ivm.customer_consolidation.orphan_customers import build_duplicate_groups

		# (TV) record is older, which would win the creation tie-break without the is_tv rule
		customers = [
			{"name": "Ashland Inc. (TV)", "customer_name": "Ashland Inc. (TV)", "creation": "2023-08-30"},
			{"name": "Ashland, Inc.", "customer_name": "Ashland, Inc.", "creation": "2023-08-31"},
		]
		classifications = {n["name"]: ("disable", "no links") for n in customers}
		link_totals = {n["name"]: 0 for n in customers}
		groups = build_duplicate_groups(customers, classifications, link_totals, set())
		self.assertEqual(groups["Ashland Inc. (TV)"]["survivor"], "Ashland, Inc.")

	def test_tv_still_wins_when_it_is_the_one_in_use(self):
		from ivm.customer_consolidation.orphan_customers import build_duplicate_groups

		customers = [
			{"name": "Foo (TV)", "customer_name": "Foo (TV)", "creation": "2023-08-31"},
			{"name": "Foo Inc", "customer_name": "Foo Inc", "creation": "2023-08-31"},
		]
		classifications = {"Foo (TV)": ("keep", "Issue.customer:2"), "Foo Inc": ("disable", "no links")}
		link_totals = {"Foo (TV)": 2, "Foo Inc": 0}
		groups = build_duplicate_groups(customers, classifications, link_totals, set())
		self.assertEqual(groups["Foo Inc"]["survivor"], "Foo (TV)")

	def test_distinct_pair_not_grouped(self):
		from ivm.customer_consolidation.orphan_customers import build_duplicate_groups

		customers = [
			{"name": "A", "customer_name": "Foo Inc", "creation": "2024-01-01"},
			{"name": "B", "customer_name": "Foo Inc", "creation": "2024-01-02"},
		]
		classifications = {"A": ("keep", "has links"), "B": ("keep", "has links")}
		link_totals = {"A": 5, "B": 3}
		distinct_pairs = {frozenset({"A", "B"})}
		groups = build_duplicate_groups(customers, classifications, link_totals, distinct_pairs)
		self.assertEqual(groups, {})


class TestReportCustomerDisposition(ERPNextTestSuite):
	"""report_customer_disposition"""

	def test_already_disabled_customer_shows_already_disabled_action(self):
		"""A customer with disabled=1 and no operational links should show proposed_action='already_disabled' and confirm='Y'."""
		from ivm.customer_consolidation.orphan_customers import report_customer_disposition

		# Create a disabled customer with no operational links
		customer = _make_customer("AlreadyDisabledTest", disabled=1)
		# Set creation date to old date so classify_customer would say "disable"
		frappe.db.set_value("Customer", customer.name, "creation", "2023-01-01 00:00:00")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Run the report with cutoff after creation date
		path = report_customer_disposition(cutoff="2024-01-01")
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and find the row
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 1, f"Expected 1 row for customer {customer.name}")
		row = rows[0]
		self.assertEqual(
			row["proposed_action"],
			"already_disabled",
			f"Expected proposed_action='already_disabled', got '{row['proposed_action']}'",
		)
		self.assertEqual(row["confirm"], "Y", f"Expected confirm='Y', got '{row['confirm']}'")

	def test_enabled_customer_needing_disable_shows_disable_action(self):
		"""A customer with disabled=0 and no operational links should show proposed_action='disable' and confirm='' (empty)."""
		from ivm.customer_consolidation.orphan_customers import report_customer_disposition

		# Create an enabled customer with no operational links
		customer = _make_customer("EnabledNeedsDisableTest", disabled=0)
		# Set creation date to old date so classify_customer would say "disable"
		frappe.db.set_value("Customer", customer.name, "creation", "2023-01-01 00:00:00")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Run the report with cutoff after creation date
		path = report_customer_disposition(cutoff="2024-01-01")
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and find the row
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 1, f"Expected 1 row for customer {customer.name}")
		row = rows[0]
		self.assertEqual(
			row["proposed_action"],
			"disable",
			f"Expected proposed_action='disable', got '{row['proposed_action']}'",
		)
		self.assertEqual(row["confirm"], "", f"Expected confirm='', got '{row['confirm']}'")

	def test_already_disabled_sorts_to_bottom(self):
		"""Customers with already_disabled action should sort after keep (rank 4 vs 3)."""
		from ivm.customer_consolidation.orphan_customers import report_customer_disposition

		# Create two customers: one enabled (needs disable), one disabled (already done)
		enabled = _make_customer("SortEnabledDisable", disabled=0)
		disabled = _make_customer("SortAlreadyDisabled", disabled=1)
		# Set creation dates to old dates so classify_customer would say "disable"
		frappe.db.set_value("Customer", enabled.name, "creation", "2023-01-01 00:00:00")
		frappe.db.set_value("Customer", disabled.name, "creation", "2023-01-01 00:00:00")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", enabled.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", disabled.name, force=True, ignore_permissions=True)
		)

		# Run the report with cutoff after creation dates
		path = report_customer_disposition(cutoff="2024-01-01")
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and check order
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = list(reader)

		# Find indices of our two customers
		enabled_idx = None
		disabled_idx = None
		for i, row in enumerate(rows):
			if row["name"] == enabled.name:
				enabled_idx = i
			elif row["name"] == disabled.name:
				disabled_idx = i

		self.assertIsNotNone(enabled_idx, f"Customer {enabled.name} not found in report")
		self.assertIsNotNone(disabled_idx, f"Customer {disabled.name} not found in report")

		# enabled (disable action, rank 0) should come before disabled (already_disabled action, rank 4)
		self.assertLess(
			enabled_idx,
			disabled_idx,
			"Expected enabled customer (disable) to sort before disabled customer (already_disabled)",
		)

		# Verify their actions
		self.assertEqual(rows[enabled_idx]["proposed_action"], "disable")
		self.assertEqual(rows[disabled_idx]["proposed_action"], "already_disabled")

	def test_disabled_customer_classified_as_review_shows_already_disabled(self):
		"""A customer with disabled=1 that the live rule would classify as 'review' (e.g., recent creation) should still show proposed_action='already_disabled' and confirm='Y'."""
		from ivm.customer_consolidation.orphan_customers import report_customer_disposition

		# Create a disabled customer with recent creation date (would be "review" if enabled)
		customer = _make_customer("DisabledReviewTest", disabled=1)
		# Set creation date to recent (within cutoff) so classify_customer would say "review"
		frappe.db.set_value("Customer", customer.name, "creation", "2024-01-15 00:00:00")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Run the report with cutoff before creation date
		path = report_customer_disposition(cutoff="2024-01-01")
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and find the row
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 1, f"Expected 1 row for customer {customer.name}")
		row = rows[0]
		# Should show already_disabled, not review, because disabled=1 takes precedence
		self.assertEqual(
			row["proposed_action"],
			"already_disabled",
			f"Expected proposed_action='already_disabled', got '{row['proposed_action']}'",
		)
		self.assertEqual(row["confirm"], "Y", f"Expected confirm='Y', got '{row['confirm']}'")

	def test_disabled_customer_classified_as_keep_shows_already_disabled(self):
		"""A customer with disabled=1 that the live rule would classify as 'keep' (e.g., has operational links) should still show proposed_action='already_disabled' and confirm='Y'."""
		from ivm.customer_consolidation.orphan_customers import report_customer_disposition

		# Create a disabled customer with an operational link (would be "keep" if enabled)
		customer = _make_customer("DisabledKeepTest", disabled=1)
		# Set creation date to old date
		frappe.db.set_value("Customer", customer.name, "creation", "2023-01-01 00:00:00")

		# Create an Issue link (operational link)
		issue = frappe.get_doc(
			{
				"doctype": "Issue",
				"subject": f"Issue_{frappe.generate_hash(length=8)}",
				"customer": customer.name,
			}
		).insert(ignore_permissions=True)

		self.addCleanup(lambda: frappe.delete_doc("Issue", issue.name, force=True, ignore_permissions=True))
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Run the report with cutoff after creation date
		path = report_customer_disposition(cutoff="2024-01-01")
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and find the row
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = [r for r in reader if r["name"] == customer.name]

		self.assertEqual(len(rows), 1, f"Expected 1 row for customer {customer.name}")
		row = rows[0]
		# Should show already_disabled, not keep, because disabled=1 takes precedence
		self.assertEqual(
			row["proposed_action"],
			"already_disabled",
			f"Expected proposed_action='already_disabled', got '{row['proposed_action']}'",
		)
		self.assertEqual(row["confirm"], "Y", f"Expected confirm='Y', got '{row['confirm']}'")

	def test_disabled_non_survivor_duplicate_shows_merge_into(self):
		"""A non-survivor duplicate-group member with disabled=1 should still show merge_into:<survivor>, not already_disabled (merge_into carve-out takes precedence)."""
		from ivm.customer_consolidation.orphan_customers import report_customer_disposition

		# Create two customers with same customer_name (will normalize to same key)
		# Use explicit customer_name to ensure they normalize to the same value
		survivor = _make_customer("DupTest1", customer_name="DuplicateCompany Inc", disabled=0)
		non_survivor = _make_customer(
			"DupTest2", customer_name="DuplicateCompany Inc", disabled=1
		)  # Same customer_name, disabled
		# Set creation dates so survivor is older (will be chosen as survivor)
		frappe.db.set_value("Customer", survivor.name, "creation", "2023-01-01 00:00:00")
		frappe.db.set_value("Customer", non_survivor.name, "creation", "2023-01-02 00:00:00")

		self.addCleanup(
			lambda: frappe.delete_doc("Customer", survivor.name, force=True, ignore_permissions=True)
		)
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", non_survivor.name, force=True, ignore_permissions=True)
		)

		# Run the report with cutoff after both creation dates
		path = report_customer_disposition(cutoff="2024-01-01")
		self.addCleanup(lambda: os.remove(path) if os.path.exists(path) else None)

		# Read CSV and find the rows
		with open(path) as f:
			reader = csv.DictReader(f)
			rows = {r["name"]: r for r in reader}

		self.assertIn(survivor.name, rows, f"Survivor {survivor.name} not found in report")
		self.assertIn(non_survivor.name, rows, f"Non-survivor {non_survivor.name} not found in report")

		survivor_row = rows[survivor.name]
		non_survivor_row = rows[non_survivor.name]

		# Survivor should be marked as survivor
		self.assertTrue(survivor_row["duplicate_group"], "Survivor should have a duplicate_group")
		self.assertEqual(
			survivor_row["proposed_survivor"], survivor.name, "Survivor's proposed_survivor should be itself"
		)

		# Non-survivor should show merge_into, not already_disabled, even though disabled=1
		self.assertTrue(non_survivor_row["duplicate_group"], "Non-survivor should have a duplicate_group")
		self.assertIn(
			"merge_into:",
			non_survivor_row["proposed_action"],
			f"Expected proposed_action to start with 'merge_into:', got '{non_survivor_row['proposed_action']}'",
		)
		self.assertEqual(
			non_survivor_row["proposed_survivor"],
			survivor.name,
			f"Non-survivor's proposed_survivor should be {survivor.name}",
		)
		self.assertEqual(
			non_survivor_row["confirm"],
			"",
			f"Non-survivor merge_into should have empty confirm, got '{non_survivor_row['confirm']}'",
		)
