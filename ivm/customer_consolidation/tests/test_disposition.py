"""Tests for ivm.customer_consolidation.disposition"""

import csv
import os
import tempfile

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation import decisions, disposition


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


class TestQueueDisablesFromReport(ERPNextTestSuite):
	"""queue_disables_from_report"""

	def test_queues_disable_rows(self):
		customer = _make_customer("DisableTest")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create a temp disposition report CSV
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"name",
					"customer_name",
					"creation",
					"disabled",
					"operational_links",
					"link_breakdown",
					"opportunity_breakdown",
					"last_opportunity_date",
					"communication_count",
					"duplicate_group",
					"proposed_survivor",
					"proposed_action",
					"reason",
					"confirm",
				],
			)
			writer.writeheader()
			writer.writerow(
				{
					"name": customer.name,
					"customer_name": customer.customer_name,
					"creation": "2024-01-01",
					"disabled": 0,
					"operational_links": 0,
					"link_breakdown": "",
					"opportunity_breakdown": "",
					"last_opportunity_date": "",
					"communication_count": 0,
					"duplicate_group": "",
					"proposed_survivor": "",
					"proposed_action": "disable",
					"reason": "no links",
					"confirm": "",
				}
			)
			temp_path = f.name

		try:
			# Patch the path
			original_path = decisions.CUSTOMERS_TO_DISABLE_PATH
			with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
				writer = csv.DictWriter(f, fieldnames=["customer", "reason", "decided_by", "date_decided"])
				writer.writeheader()
				temp_delete_path = f.name

			try:
				decisions.CUSTOMERS_TO_DISABLE_PATH = temp_delete_path
				result = disposition.queue_disables_from_report(temp_path)
				self.assertEqual(result["queued"], 1)
				self.assertEqual(result["skipped_already_queued"], 0)

				# Verify it was written
				with open(temp_delete_path) as f:
					reader = csv.DictReader(f)
					rows = list(reader)
				self.assertEqual(len(rows), 1)
				self.assertEqual(rows[0]["customer"], customer.name)
			finally:
				decisions.CUSTOMERS_TO_DISABLE_PATH = original_path
				os.remove(temp_delete_path)
		finally:
			os.remove(temp_path)

	def test_skips_already_queued(self):
		customer = _make_customer("AlreadyQueued")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create temp CSV with the customer already queued
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(f, fieldnames=["customer", "reason", "decided_by", "date_decided"])
			writer.writeheader()
			writer.writerow(
				{
					"customer": customer.name,
					"reason": "old",
					"decided_by": "rule",
					"date_decided": "2024-01-01",
				}
			)
			temp_delete_path = f.name

		# Create disposition report
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"name",
					"customer_name",
					"creation",
					"disabled",
					"operational_links",
					"link_breakdown",
					"opportunity_breakdown",
					"last_opportunity_date",
					"communication_count",
					"duplicate_group",
					"proposed_survivor",
					"proposed_action",
					"reason",
					"confirm",
				],
			)
			writer.writeheader()
			writer.writerow(
				{
					"name": customer.name,
					"customer_name": customer.customer_name,
					"creation": "2024-01-01",
					"disabled": 0,
					"operational_links": 0,
					"link_breakdown": "",
					"opportunity_breakdown": "",
					"last_opportunity_date": "",
					"communication_count": 0,
					"duplicate_group": "",
					"proposed_survivor": "",
					"proposed_action": "disable",
					"reason": "no links",
					"confirm": "",
				}
			)
			temp_report_path = f.name

		try:
			original_path = decisions.CUSTOMERS_TO_DISABLE_PATH
			decisions.CUSTOMERS_TO_DISABLE_PATH = temp_delete_path
			result = disposition.queue_disables_from_report(temp_report_path)
			self.assertEqual(result["queued"], 0)
			self.assertEqual(result["skipped_already_queued"], 1)
			decisions.CUSTOMERS_TO_DISABLE_PATH = original_path
		finally:
			os.remove(temp_delete_path)
			os.remove(temp_report_path)


class TestQueueReviewDecisionsFromReport(ERPNextTestSuite):
	"""queue_review_decisions_from_report"""

	def test_queues_review_rows_with_disable_confirm(self):
		customer = _make_customer("ReviewDisable")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create disposition report with review row
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"name",
					"customer_name",
					"creation",
					"disabled",
					"operational_links",
					"link_breakdown",
					"opportunity_breakdown",
					"last_opportunity_date",
					"communication_count",
					"duplicate_group",
					"proposed_survivor",
					"proposed_action",
					"reason",
					"confirm",
				],
			)
			writer.writeheader()
			writer.writerow(
				{
					"name": customer.name,
					"customer_name": customer.customer_name,
					"creation": "2024-01-01",
					"disabled": 0,
					"operational_links": 0,
					"link_breakdown": "",
					"opportunity_breakdown": "",
					"last_opportunity_date": "",
					"communication_count": 0,
					"duplicate_group": "",
					"proposed_survivor": "",
					"proposed_action": "review",
					"reason": "recent creation",
					"confirm": "disable",
				}
			)
			temp_report_path = f.name

		try:
			with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
				writer = csv.DictWriter(f, fieldnames=["customer", "reason", "decided_by", "date_decided"])
				writer.writeheader()
				temp_delete_path = f.name

			try:
				original_path = decisions.CUSTOMERS_TO_DISABLE_PATH
				decisions.CUSTOMERS_TO_DISABLE_PATH = temp_delete_path
				result = disposition.queue_review_decisions_from_report(temp_report_path)
				self.assertEqual(result["queued"], 1)
				decisions.CUSTOMERS_TO_DISABLE_PATH = original_path
			finally:
				os.remove(temp_delete_path)
		finally:
			os.remove(temp_report_path)

	def test_skips_review_rows_without_disable_confirm(self):
		customer = _make_customer("ReviewNoConfirm")
		self.addCleanup(
			lambda: frappe.delete_doc("Customer", customer.name, force=True, ignore_permissions=True)
		)

		# Create disposition report with review row but no confirm
		with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"name",
					"customer_name",
					"creation",
					"disabled",
					"operational_links",
					"link_breakdown",
					"opportunity_breakdown",
					"last_opportunity_date",
					"communication_count",
					"duplicate_group",
					"proposed_survivor",
					"proposed_action",
					"reason",
					"confirm",
				],
			)
			writer.writeheader()
			writer.writerow(
				{
					"name": customer.name,
					"customer_name": customer.customer_name,
					"creation": "2024-01-01",
					"disabled": 0,
					"operational_links": 0,
					"link_breakdown": "",
					"opportunity_breakdown": "",
					"last_opportunity_date": "",
					"communication_count": 0,
					"duplicate_group": "",
					"proposed_survivor": "",
					"proposed_action": "review",
					"reason": "recent creation",
					"confirm": "",
				}
			)
			temp_report_path = f.name

		try:
			with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as f:
				writer = csv.DictWriter(f, fieldnames=["customer", "reason", "decided_by", "date_decided"])
				writer.writeheader()
				temp_delete_path = f.name

			try:
				original_path = decisions.CUSTOMERS_TO_DISABLE_PATH
				decisions.CUSTOMERS_TO_DISABLE_PATH = temp_delete_path
				result = disposition.queue_review_decisions_from_report(temp_report_path)
				self.assertEqual(result["queued"], 0)
				decisions.CUSTOMERS_TO_DISABLE_PATH = original_path
			finally:
				os.remove(temp_delete_path)
		finally:
			os.remove(temp_report_path)
