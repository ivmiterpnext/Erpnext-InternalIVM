"""Integration tests for ivm.warehouse.services.delivery_note"""

import frappe
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.tests.utils import ERPNextTestSuite

from ivm.warehouse.services.delivery_note import create_delivery_note_from_warehouse_request
from ivm.warehouse.services.pick_list import add_item_to_pick_list, create_pick_list

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
TARGET_WAREHOUSE = "_Test Warehouse 1 - _TC"


def _make_warehouse_request(**kwargs):
	"""Create a minimal Warehouse Request for testing."""
	doc = frappe.get_doc(
		{
			"doctype": "Warehouse Request",
			"request_reason": kwargs.get("request_reason", "Shipping Request"),
			"subject": kwargs.get("subject", "Test WR"),
			"customer": kwargs.get("customer"),
			"related_project": kwargs.get("related_project"),
			"source_build_request": kwargs.get("source_build_request"),
			"non_inventory_shipment": kwargs.get("non_inventory_shipment", 0),
			"notes": kwargs.get("notes"),
			"status": kwargs.get("status", "New"),
		}
	)
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


def _make_customer():
	"""Create a test customer."""
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": frappe.generate_hash(length=10),
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
		}
	)
	customer.insert(ignore_permissions=True)
	return customer


def _set_default_company():
	"""Set global default company."""
	frappe.db.set_single_value("Global Defaults", "default_company", COMPANY)


def _ensure_non_inventory_item():
	"""Ensure Non-Inventory Shipment item exists."""
	if not frappe.db.exists("Item", "Non-Inventory Shipment"):
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "Non-Inventory Shipment",
				"item_name": "Non-Inventory Shipment",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)


def _make_build_wr_with_submitted_stock_entry(customer=None):
	"""Create a Build WR with a submitted pick list and submitted stock entry."""
	item = make_item()
	_seed_stock(item.name)

	pl_name = create_pick_list(COMPANY)
	add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

	wr = _make_warehouse_request(
		request_reason="Build Machine",
		pick_list=pl_name,
		customer=customer,
	)

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
	se.custom_warehouse_request = wr.name
	se.submit()

	frappe.db.set_value("Warehouse Request", wr.name, "status", "Crated - Ready to Ship")

	return wr


class TestCreateDeliveryNoteNormalFlow(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — normal flow"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_creates_submitted_delivery_note_with_items(self):
		customer = _make_customer()
		item = make_item()
		_seed_stock(item.name)

		pl_name = create_pick_list(COMPANY)
		add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

		wr = _make_warehouse_request(customer=customer.name)

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
		se.custom_warehouse_request = wr.name
		se.submit()

		dn_name = create_delivery_note_from_warehouse_request(wr.name)
		self.assertTrue(dn_name)

		dn = frappe.get_doc("Delivery Note", dn_name)
		self.assertEqual(dn.docstatus, 1)
		self.assertEqual(dn.customer, customer.name)
		self.assertEqual(dn.custom_related_warehouse_request, wr.name)
		self.assertEqual(len(dn.items), 1)
		self.assertEqual(dn.items[0].item_code, item.name)
		self.assertEqual(dn.items[0].qty, 5)

	def test_returns_delivery_note_name(self):
		customer = _make_customer()
		item = make_item()
		_seed_stock(item.name)

		pl_name = create_pick_list(COMPANY)
		add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

		wr = _make_warehouse_request(customer=customer.name)

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
		se.custom_warehouse_request = wr.name
		se.submit()

		dn_name = create_delivery_note_from_warehouse_request(wr.name)
		self.assertIsInstance(dn_name, str)
		self.assertTrue(frappe.db.exists("Delivery Note", dn_name))


class TestCreateDeliveryNoteExistingDN(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — existing DN handling"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_returns_existing_dn_when_not_cancelled(self):
		customer = _make_customer()
		item = make_item()
		_seed_stock(item.name)

		pl_name = create_pick_list(COMPANY)
		add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

		wr = _make_warehouse_request(customer=customer.name)

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
		se.custom_warehouse_request = wr.name
		se.submit()

		first_dn_name = create_delivery_note_from_warehouse_request(wr.name)
		second_dn_name = create_delivery_note_from_warehouse_request(wr.name)

		self.assertEqual(first_dn_name, second_dn_name)

	def test_shows_msgprint_when_dn_exists(self):
		customer = _make_customer()
		item = make_item()
		_seed_stock(item.name)

		pl_name = create_pick_list(COMPANY)
		add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

		wr = _make_warehouse_request(customer=customer.name)

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
		se.custom_warehouse_request = wr.name
		se.submit()

		first_dn_name = create_delivery_note_from_warehouse_request(wr.name)

		frappe.clear_messages()
		second_dn_name = create_delivery_note_from_warehouse_request(wr.name)

		messages = frappe.get_message_log()
		self.assertTrue(any("already exists" in str(msg) for msg in messages))
		self.assertEqual(first_dn_name, second_dn_name)


class TestCreateDeliveryNoteSourceBuildRequest(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — source_build_request handling"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_pulls_items_from_build_wr_stock_entries(self):
		customer = _make_customer()
		build_wr = _make_build_wr_with_submitted_stock_entry(customer=customer.name)

		shipping_wr = _make_warehouse_request(
			customer=customer.name,
			source_build_request=build_wr.name,
		)

		dn_name = create_delivery_note_from_warehouse_request(shipping_wr.name)
		self.assertTrue(dn_name)

		dn = frappe.get_doc("Delivery Note", dn_name)
		self.assertEqual(len(dn.items), 1)
		self.assertEqual(dn.items[0].qty, 5)

	def test_sets_build_wr_status_to_closed(self):
		customer = _make_customer()
		build_wr = _make_build_wr_with_submitted_stock_entry(customer=customer.name)

		shipping_wr = _make_warehouse_request(
			customer=customer.name,
			source_build_request=build_wr.name,
		)

		create_delivery_note_from_warehouse_request(shipping_wr.name)

		build_wr.reload()
		self.assertEqual(build_wr.status, "Closed")


class TestCreateDeliveryNoteNonInventory(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — non-inventory shipment"""

	def setUp(self):
		super().setUp()
		_set_default_company()
		_ensure_non_inventory_item()

	def test_creates_dn_with_placeholder_item_when_no_stock_entries(self):
		customer = _make_customer()

		wr = _make_warehouse_request(
			customer=customer.name,
			non_inventory_shipment=1,
			notes="Test non-inventory shipment",
		)

		dn_name = create_delivery_note_from_warehouse_request(wr.name)
		self.assertTrue(dn_name)

		dn = frappe.get_doc("Delivery Note", dn_name)
		self.assertEqual(len(dn.items), 1)
		self.assertEqual(dn.items[0].item_code, "Non-Inventory Shipment")
		self.assertEqual(dn.items[0].qty, 1)

	def test_placeholder_item_uses_wr_notes_as_description(self):
		customer = _make_customer()
		notes_text = "Custom shipment notes"

		wr = _make_warehouse_request(
			customer=customer.name,
			non_inventory_shipment=1,
			notes=notes_text,
		)

		dn_name = create_delivery_note_from_warehouse_request(wr.name)
		dn = frappe.get_doc("Delivery Note", dn_name)
		self.assertEqual(dn.items[0].description, notes_text)

	def test_placeholder_item_default_description_when_no_notes(self):
		customer = _make_customer()

		wr = _make_warehouse_request(
			customer=customer.name,
			non_inventory_shipment=1,
		)

		dn_name = create_delivery_note_from_warehouse_request(wr.name)
		dn = frappe.get_doc("Delivery Note", dn_name)
		self.assertIn("Non-inventory shipment", dn.items[0].description)


class TestCreateDeliveryNoteNoItems(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — no items, not non-inventory"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_logs_error_and_returns_none_when_no_items(self):
		customer = _make_customer()

		wr = _make_warehouse_request(
			customer=customer.name,
			non_inventory_shipment=0,
		)

		result = create_delivery_note_from_warehouse_request(wr.name)
		self.assertIsNone(result)

	def test_no_delivery_note_created_when_no_items(self):
		customer = _make_customer()

		wr = _make_warehouse_request(
			customer=customer.name,
			non_inventory_shipment=0,
		)

		create_delivery_note_from_warehouse_request(wr.name)

		dn_count = frappe.db.count(
			"Delivery Note",
			{"custom_related_warehouse_request": wr.name},
		)
		self.assertEqual(dn_count, 0)


class TestCreateDeliveryNoteNoCustomer(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — missing customer"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_raises_when_no_customer(self):
		item = make_item()
		_seed_stock(item.name)

		pl_name = create_pick_list(COMPANY)
		add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

		wr = _make_warehouse_request(customer=None)

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
		se.custom_warehouse_request = wr.name
		se.submit()

		with self.assertRaises(frappe.ValidationError):
			create_delivery_note_from_warehouse_request(wr.name)


class TestCreateDeliveryNoteCompanyResolution(ERPNextTestSuite):
	"""create_delivery_note_from_warehouse_request — company resolution"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_uses_global_default_company(self):
		customer = _make_customer()
		item = make_item()
		_seed_stock(item.name)

		pl_name = create_pick_list(COMPANY)
		add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)

		wr = _make_warehouse_request(customer=customer.name)

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
		se.custom_warehouse_request = wr.name
		se.submit()

		dn_name = create_delivery_note_from_warehouse_request(wr.name)
		dn = frappe.get_doc("Delivery Note", dn_name)
		self.assertEqual(dn.company, COMPANY)
