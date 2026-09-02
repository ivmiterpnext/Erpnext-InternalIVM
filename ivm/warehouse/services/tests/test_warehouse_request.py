"""Integration tests for ivm.warehouse.services.warehouse_request"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from ivm.warehouse.services.warehouse_request import (
	create_build_requests_from_detail_rows,
	create_shipping_request_from_build,
	get_equipment_info_task,
	get_or_create_warehouse_request_pick_list,
	get_warehouse_request_linked_docs,
	reset_warehouse_request_pick_list,
	send_equipment_info_to_ics,
)
from ivm.warehouse.services.pick_list import add_item_to_pick_list

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
TARGET_WAREHOUSE = "_Test Warehouse 1 - _TC"


def _make_warehouse_request(**kwargs):
	"""Create a minimal Warehouse Request for testing."""
	doc = frappe.get_doc({
		"doctype": "Warehouse Request",
		"request_reason": kwargs.get("request_reason", "Build Machine"),
		"subject": kwargs.get("subject", "Test WR"),
		"customer": kwargs.get("customer"),
		"related_project": kwargs.get("related_project"),
		"schema_version": kwargs.get("schema_version", 2),
		"status": kwargs.get("status", "New"),
		"machine_name": kwargs.get("machine_name"),
		"pick_list": kwargs.get("pick_list"),
	})
	doc.insert(ignore_permissions=True)
	return doc


def _seed_stock(item_code, warehouse=WAREHOUSE, qty=100, rate=10):
	se = make_stock_entry(
		item_code=item_code,
		qty=qty,
		basic_rate=rate,
		to_warehouse=warehouse,
		company=COMPANY,
		stock_entry_type="Material Receipt",
	)
	se.submit()


def _ensure_task_type():
	"""Ensure the 'add machine info' Task Type exists on the test site."""
	if not frappe.db.exists("Task Type", "add machine info"):
		frappe.get_doc({
			"doctype": "Task Type",
			"name": "add machine info",
		}).insert(ignore_permissions=True)


def _set_default_company():
	"""Set global default company so pick list creation resolves correctly."""
	frappe.db.set_single_value("Global Defaults", "default_company", COMPANY)


def _make_build_wr_with_submitted_stock_entry():
	"""Create a Build WR with a submitted pick list and submitted stock entry."""
	item = make_item()
	_seed_stock(item.name)

	from ivm.warehouse.services.pick_list import create_pick_list
	pl_name = create_pick_list(COMPANY)
	add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

	wr = _make_warehouse_request(request_reason="Build Machine", pick_list=pl_name)

	pl = frappe.get_doc("Pick List", pl_name)
	pl.submit()

	se = make_stock_entry(
		item_code=item.name,
		qty=5,
		from_warehouse=WAREHOUSE,
		to_warehouse=TARGET_WAREHOUSE,
		company=COMPANY,
		stock_entry_type="Material Transfer",
		do_not_submit=True,
	)
	se.pick_list = pl_name
	se.submit()

	wr.reload()
	wr.status = "Crated - Ready to Ship"
	wr.save(ignore_permissions=True)

	return wr


class TestGetOrCreatePickList(ERPNextTestSuite):
	"""get_or_create_warehouse_request_pick_list"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_creates_pick_list_when_none_exists(self):
		wr = _make_warehouse_request()
		result = get_or_create_warehouse_request_pick_list(wr.name)
		self.assertIn("pick_list", result)
		self.assertTrue(result["pick_list"])
		self.assertFalse(result["submitted"])
		self.assertEqual(result["items"], [])

	def test_returns_existing_pick_list(self):
		wr = _make_warehouse_request()
		first = get_or_create_warehouse_request_pick_list(wr.name)
		second = get_or_create_warehouse_request_pick_list(wr.name)
		self.assertEqual(first["pick_list"], second["pick_list"])

	def test_links_pick_list_to_warehouse_request(self):
		wr = _make_warehouse_request()
		result = get_or_create_warehouse_request_pick_list(wr.name)
		linked_pl = frappe.db.get_value("Warehouse Request", wr.name, "pick_list")
		self.assertEqual(linked_pl, result["pick_list"])


class TestGetLinkedDocs(ERPNextTestSuite):
	"""get_warehouse_request_linked_docs"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_no_pick_list_returns_empty(self):
		wr = _make_warehouse_request()
		result = get_warehouse_request_linked_docs(wr.name)
		self.assertIsNone(result["pick_list"])
		self.assertFalse(result["pick_list_submitted"])
		self.assertIsNone(result["stock_entry"])
		self.assertIsNone(result["delivery_note"])

	def test_draft_pick_list_not_submitted(self):
		wr = _make_warehouse_request()
		get_or_create_warehouse_request_pick_list(wr.name)
		result = get_warehouse_request_linked_docs(wr.name)
		self.assertIsNotNone(result["pick_list"])
		self.assertFalse(result["pick_list_submitted"])

	def test_submitted_pick_list_flagged(self):
		item = make_item()
		_seed_stock(item.name)
		wr = _make_warehouse_request()
		pl_result = get_or_create_warehouse_request_pick_list(wr.name)
		add_item_to_pick_list(pl_result["pick_list"], item.name, WAREHOUSE, 5)
		frappe.get_doc("Pick List", pl_result["pick_list"]).submit()
		result = get_warehouse_request_linked_docs(wr.name)
		self.assertTrue(result["pick_list_submitted"])


class TestResetPickList(ERPNextTestSuite):
	"""reset_warehouse_request_pick_list"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_reset_clears_link_and_deletes_pick_list(self):
		wr = _make_warehouse_request()
		pl_result = get_or_create_warehouse_request_pick_list(wr.name)
		pl_name = pl_result["pick_list"]
		result = reset_warehouse_request_pick_list(wr.name)
		self.assertTrue(result["success"])
		self.assertIsNone(frappe.db.get_value("Warehouse Request", wr.name, "pick_list"))
		self.assertFalse(frappe.db.exists("Pick List", pl_name))

	def test_reset_no_pick_list_returns_failure(self):
		wr = _make_warehouse_request()
		result = reset_warehouse_request_pick_list(wr.name)
		self.assertFalse(result["success"])


class TestCreateShippingRequest(ERPNextTestSuite):
	"""create_shipping_request_from_build"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_creates_shipping_request(self):
		build_wr = _make_build_wr_with_submitted_stock_entry()
		shipping_name = create_shipping_request_from_build(build_wr.name)
		self.assertTrue(shipping_name)
		shipping_wr = frappe.get_doc("Warehouse Request", shipping_name)
		self.assertEqual(shipping_wr.request_reason, "Shipping Request")
		self.assertEqual(shipping_wr.source_build_request, build_wr.name)
		self.assertEqual(shipping_wr.related_project, build_wr.related_project)
		self.assertEqual(shipping_wr.customer, build_wr.customer)

	def test_returns_existing_shipping_request(self):
		build_wr = _make_build_wr_with_submitted_stock_entry()
		first = create_shipping_request_from_build(build_wr.name)
		second = create_shipping_request_from_build(build_wr.name)
		self.assertEqual(first, second)

	def test_non_build_request_raises(self):
		wr = _make_warehouse_request(request_reason="Shipping Request")
		with self.assertRaises(frappe.ValidationError):
			create_shipping_request_from_build(wr.name)

	def test_wrong_status_raises(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		with self.assertRaises(frappe.ValidationError):
			create_shipping_request_from_build(wr.name)


class TestGetEquipmentInfoTask(ERPNextTestSuite):
	"""get_equipment_info_task"""

	def setUp(self):
		super().setUp()
		_ensure_task_type()

	def test_returns_none_when_no_task(self):
		wr = _make_warehouse_request()
		result = get_equipment_info_task(wr.name)
		self.assertIsNone(result)

	def test_returns_task_name(self):
		wr = _make_warehouse_request()
		task = frappe.get_doc({
			"doctype": "Task",
			"subject": "Test equipment info task",
			"type": "add machine info",
			"custom_warehouse_request": wr.name,
		})
		task.insert(ignore_permissions=True)
		result = get_equipment_info_task(wr.name)
		self.assertEqual(result, task.name)


class TestSendEquipmentInfoToIcs(ERPNextTestSuite):
	"""send_equipment_info_to_ics"""

	def setUp(self):
		super().setUp()
		_ensure_task_type()

	def test_creates_task(self):
		wr = _make_warehouse_request(
			request_reason="Build Machine",
			machine_name="TEST-MACHINE-001",
		)
		task_name = send_equipment_info_to_ics(wr.name)
		self.assertTrue(task_name)
		task = frappe.get_doc("Task", task_name)
		self.assertEqual(task.type, "add machine info")
		self.assertEqual(task.custom_warehouse_request, wr.name)
		self.assertEqual(task.custom_assigned_to, wr.owner)

	def test_returns_existing_task(self):
		wr = _make_warehouse_request(
			request_reason="Build Machine",
			machine_name="TEST-MACHINE-002",
		)
		first = send_equipment_info_to_ics(wr.name)
		second = send_equipment_info_to_ics(wr.name)
		self.assertEqual(first, second)

	def test_non_build_raises(self):
		wr = _make_warehouse_request(request_reason="Shipping Request")
		with self.assertRaises(frappe.ValidationError):
			send_equipment_info_to_ics(wr.name)

	def test_schema_v1_raises(self):
		wr = _make_warehouse_request(
			request_reason="Build Machine",
			schema_version=1,
		)
		with self.assertRaises(frappe.ValidationError):
			send_equipment_info_to_ics(wr.name)


class TestCreateBuildRequestsFromDetailRows(ERPNextTestSuite):
	"""create_build_requests_from_detail_rows — with mocked iCorp API"""

	def test_unknown_detail_table_raises(self):
		with self.assertRaises(frappe.ValidationError):
			create_build_requests_from_detail_rows("PROJ-0001", "nonexistent_table")

	@patch("ivm.warehouse.services.warehouse_request.fetch_machine")
	def test_creates_requests_for_each_row(self, mock_fetch):
		mock_fetch.return_value = {
			"icorp_machine_id": 12345,
			"serial_number": "SN-001",
			"prose_number": "PN-001",
		}

		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": frappe.generate_hash(length=10),
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
			"icorp_client_id": "TEST-CLIENT-ID",
		})
		customer.insert(ignore_permissions=True)

		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": f"Test Project - {frappe.generate_hash(length=6)}",
			"customer": customer.name,
			"company": COMPANY,
		})
		project.insert(ignore_permissions=True)

		project.append("custom_deployment_smartstation_details", {
			"machine_name": f"MACH-{frappe.generate_hash(length=6)}",
		})
		project.save(ignore_permissions=True)

		result = create_build_requests_from_detail_rows(
			project.name, "custom_deployment_smartstation_details"
		)
		self.assertEqual(len(result["created"]), 1)
		self.assertEqual(len(result["failed"]), 0)

		wr = frappe.get_doc("Warehouse Request", result["created"][0])
		self.assertEqual(wr.request_reason, "Build Machine")
		self.assertEqual(wr.related_project, project.name)
		self.assertEqual(wr.customer, customer.name)
		self.assertEqual(wr.schema_version, 2)
		self.assertEqual(wr.icorp_machine_id, 12345)

	@patch("ivm.warehouse.services.warehouse_request.fetch_machine")
	def test_skips_existing_requests(self, mock_fetch):
		mock_fetch.return_value = {
			"icorp_machine_id": 99999,
			"serial_number": "SN-SKIP",
			"prose_number": "PN-SKIP",
		}

		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": frappe.generate_hash(length=10),
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
			"icorp_client_id": "TEST-CLIENT-SKIP",
		})
		customer.insert(ignore_permissions=True)

		machine_name = f"MACH-{frappe.generate_hash(length=6)}"
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": f"Test Project - {frappe.generate_hash(length=6)}",
			"customer": customer.name,
			"company": COMPANY,
		})
		project.insert(ignore_permissions=True)
		project.append("custom_deployment_smartstation_details", {
			"machine_name": machine_name,
		})
		project.save(ignore_permissions=True)

		first = create_build_requests_from_detail_rows(
			project.name, "custom_deployment_smartstation_details"
		)
		self.assertEqual(len(first["created"]), 1)

		second = create_build_requests_from_detail_rows(
			project.name, "custom_deployment_smartstation_details"
		)
		self.assertEqual(len(second["created"]), 0)
		self.assertEqual(second["skipped"], 1)

	@patch("ivm.warehouse.services.warehouse_request.fetch_machine")
	def test_failed_lookup_returns_failures(self, mock_fetch):
		mock_fetch.return_value = None

		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": frappe.generate_hash(length=10),
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
			"icorp_client_id": "TEST-CLIENT-FAIL",
		})
		customer.insert(ignore_permissions=True)

		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": f"Test Project - {frappe.generate_hash(length=6)}",
			"customer": customer.name,
			"company": COMPANY,
		})
		project.insert(ignore_permissions=True)
		project.append("custom_deployment_smartstation_details", {
			"machine_name": "WILL-FAIL",
		})
		project.save(ignore_permissions=True)

		result = create_build_requests_from_detail_rows(
			project.name, "custom_deployment_smartstation_details"
		)
		self.assertEqual(len(result["created"]), 0)
		self.assertIn("WILL-FAIL", result["failed"])

	def test_no_customer_raises(self):
		project = frappe.get_doc({
			"doctype": "Project",
			"project_name": f"No Customer Project - {frappe.generate_hash(length=6)}",
			"company": COMPANY,
		})
		project.insert(ignore_permissions=True)
		project.append("custom_deployment_smartstation_details", {
			"machine_name": "MACH-NO-CUST",
		})
		project.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			create_build_requests_from_detail_rows(
				project.name, "custom_deployment_smartstation_details"
			)
