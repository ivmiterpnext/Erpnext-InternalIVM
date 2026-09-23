"""Integration tests for the Warehouse Request DocType controller
(ivm.ivm.doctype.warehouse_request.warehouse_request) -- validate() and on_update().

Note: this is distinct from ivm/warehouse/services/tests/test_warehouse_request.py,
which tests the *service-layer* module of the same name.
"""

from unittest.mock import patch

import frappe
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry
from erpnext.tests.utils import ERPNextTestSuite

from ivm.warehouse.services.pick_list import add_item_to_pick_list, create_pick_list

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
TARGET_WAREHOUSE = "_Test Warehouse 1 - _TC"

_DN_PATCH_TARGET = "ivm.warehouse.services.delivery_note.create_delivery_note_from_warehouse_request"


def _set_default_company():
	frappe.db.set_single_value("Global Defaults", "default_company", COMPANY)


def _make_warehouse_request(**kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Warehouse Request",
			"request_reason": kwargs.get("request_reason", "Build Machine"),
			"subject": kwargs.get("subject", "Test WR"),
			"customer": kwargs.get("customer"),
			"status": kwargs.get("status", "New"),
			"pick_list": kwargs.get("pick_list"),
			"non_inventory_shipment": kwargs.get("non_inventory_shipment", 0),
			"rfid_settings": kwargs.get("rfid_settings", []),
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


def _make_build_wr_with_pick_list_stock_entry(submit_stock_entry=True):
	"""Build WR with a submitted Pick List and a Material Transfer Stock Entry
	linked via `pick_list` (feeds _validate_crated_status)."""
	item = make_item()
	_seed_stock(item.name)
	pl_name = create_pick_list(COMPANY)
	add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)
	wr = _make_warehouse_request(request_reason="Build Machine", pick_list=pl_name)
	frappe.get_doc("Pick List", pl_name).submit()

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
	if submit_stock_entry:
		se.submit()
	else:
		se.save(ignore_permissions=True)
	return wr, se, pl_name


def _make_shipping_wr_with_material_transfer(submit_stock_entry=True):
	"""Shipping Request WR with a pick_list and a Stock Entry linked via
	`custom_warehouse_request` (feeds _validate_closed_status)."""
	item = make_item()
	_seed_stock(item.name)
	pl_name = create_pick_list(COMPANY)
	add_item_to_pick_list(pl_name, item.name, WAREHOUSE, 5)
	wr = _make_warehouse_request(request_reason="Shipping Request", pick_list=pl_name)
	frappe.get_doc("Pick List", pl_name).submit()

	se = make_stock_entry(
		item_code=item.name,
		qty=5,
		from_warehouse=WAREHOUSE,
		to_warehouse=TARGET_WAREHOUSE,
		company=COMPANY,
		stock_entry_type="Material Transfer",
		do_not_submit=True,
	)
	se.custom_warehouse_request = wr.name
	if submit_stock_entry:
		se.submit()
	else:
		se.save(ignore_permissions=True)
	return wr, se


class TestValidateRfidSettings(ERPNextTestSuite):
	"""validate: _validate_rfid_settings"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_five_rows_allowed(self):
		wr = _make_warehouse_request(rfid_settings=[{} for _ in range(5)])
		self.assertEqual(len(wr.rfid_settings), 5)

	def test_six_rows_throws(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			_make_warehouse_request(rfid_settings=[{} for _ in range(6)])
		self.assertIn("up to 5", str(ctx.exception))

	def test_zero_rows_allowed(self):
		wr = _make_warehouse_request(rfid_settings=[])
		self.assertEqual(len(wr.rfid_settings), 0)


class TestValidateNonInventoryShipment(ERPNextTestSuite):
	"""validate: _validate_non_inventory_shipment"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_blocked_when_pick_list_exists(self):
		pl_name = create_pick_list(COMPANY)
		with self.assertRaises(frappe.ValidationError):
			_make_warehouse_request(pick_list=pl_name, non_inventory_shipment=1)

	def test_allowed_without_pick_list(self):
		wr = _make_warehouse_request(non_inventory_shipment=1)
		self.assertTrue(wr.non_inventory_shipment)

	def test_pick_list_allowed_without_flag(self):
		pl_name = create_pick_list(COMPANY)
		wr = _make_warehouse_request(pick_list=pl_name, non_inventory_shipment=0)
		self.assertEqual(wr.pick_list, pl_name)


class TestValidateCratedStatus(ERPNextTestSuite):
	"""validate: _validate_crated_status"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_non_build_reason_skips_check(self):
		wr = _make_warehouse_request(request_reason="Shipping Request", status="New")
		wr.status = "Crated - Ready to Ship"
		wr.save(ignore_permissions=True)  # no throw: reason doesn't start with "Build"

	def test_non_crated_status_skips_check(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		self.assertEqual(wr.status, "New")

	def test_crated_without_pick_list_throws(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		wr.status = "Crated - Ready to Ship"
		with self.assertRaises(frappe.ValidationError) as ctx:
			wr.save(ignore_permissions=True)
		self.assertIn("without a Pick List", str(ctx.exception))

	def test_crated_with_pick_list_no_stock_entry_throws(self):
		pl_name = create_pick_list(COMPANY)
		wr = _make_warehouse_request(request_reason="Build Machine", pick_list=pl_name, status="New")
		wr.status = "Crated - Ready to Ship"
		with self.assertRaises(frappe.ValidationError) as ctx:
			wr.save(ignore_permissions=True)
		self.assertIn("no Stock Entry", str(ctx.exception))

	def test_crated_with_draft_stock_entry_throws(self):
		wr, _se, _pl_name = _make_build_wr_with_pick_list_stock_entry(submit_stock_entry=False)
		wr.reload()
		wr.status = "Crated - Ready to Ship"
		with self.assertRaises(frappe.ValidationError) as ctx:
			wr.save(ignore_permissions=True)
		self.assertIn("still in draft", str(ctx.exception))

	def test_crated_with_submitted_stock_entry_passes(self):
		wr, _se, _pl_name = _make_build_wr_with_pick_list_stock_entry(submit_stock_entry=True)
		wr.reload()
		wr.status = "Crated - Ready to Ship"
		wr.save(ignore_permissions=True)
		self.assertEqual(wr.status, "Crated - Ready to Ship")


class TestValidateClosedStatus(ERPNextTestSuite):
	"""validate: _validate_closed_status"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_non_shipping_reason_skips_check(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		wr.status = "Closed"
		wr.save(ignore_permissions=True)  # no throw

	def test_non_inventory_shipment_skips_check(self):
		wr = _make_warehouse_request(
			request_reason="Shipping Request",
			non_inventory_shipment=1,
			status="New",
		)
		with patch(_DN_PATCH_TARGET):
			wr.status = "Closed"
			wr.save(ignore_permissions=True)  # no throw

	def test_closed_without_pick_list_throws(self):
		wr = _make_warehouse_request(request_reason="Shipping Request", status="New")
		wr.status = "Closed"
		with self.assertRaises(frappe.ValidationError) as ctx:
			wr.save(ignore_permissions=True)
		self.assertIn("without a Pick List", str(ctx.exception))

	def test_closed_no_material_transfer_throws(self):
		pl_name = create_pick_list(COMPANY)
		wr = _make_warehouse_request(request_reason="Shipping Request", pick_list=pl_name, status="New")
		wr.status = "Closed"
		with self.assertRaises(frappe.ValidationError) as ctx:
			wr.save(ignore_permissions=True)
		self.assertIn("no Stock Entry (Material Transfer)", str(ctx.exception))

	def test_closed_draft_material_transfer_throws(self):
		wr, _se = _make_shipping_wr_with_material_transfer(submit_stock_entry=False)
		wr.reload()
		wr.status = "Closed"
		with self.assertRaises(frappe.ValidationError) as ctx:
			wr.save(ignore_permissions=True)
		self.assertIn("still in draft", str(ctx.exception))

	def test_closed_submitted_material_transfer_passes(self):
		wr, _se = _make_shipping_wr_with_material_transfer(submit_stock_entry=True)
		wr.reload()
		with patch(_DN_PATCH_TARGET):
			wr.status = "Closed"
			wr.save(ignore_permissions=True)
		self.assertEqual(wr.status, "Closed")


class TestOnUpdateAutoCreateDeliveryNote(ERPNextTestSuite):
	"""on_update: auto-create Delivery Note on transition to Closed"""

	def setUp(self):
		super().setUp()
		_set_default_company()

	def test_creates_delivery_note_on_transition_to_closed(self):
		wr, _se = _make_shipping_wr_with_material_transfer(submit_stock_entry=True)
		wr.reload()
		with patch(_DN_PATCH_TARGET) as mock_create:
			wr.status = "Closed"
			wr.save(ignore_permissions=True)
			mock_create.assert_called_once_with(wr.name)

	def test_no_delivery_note_for_non_shipping_reason(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		with patch(_DN_PATCH_TARGET) as mock_create:
			wr.status = "Closed"
			wr.save(ignore_permissions=True)
			mock_create.assert_not_called()

	def test_no_delivery_note_when_status_unchanged(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		with patch(_DN_PATCH_TARGET) as mock_create:
			wr.subject = "Updated subject"
			wr.save(ignore_permissions=True)
			mock_create.assert_not_called()

	def test_no_delivery_note_when_already_closed(self):
		wr = _make_warehouse_request(request_reason="Build Machine", status="New")
		with patch(_DN_PATCH_TARGET):
			wr.status = "Closed"
			wr.save(ignore_permissions=True)
		with patch(_DN_PATCH_TARGET) as mock_create:
			wr.subject = "Touch again"
			wr.save(ignore_permissions=True)
			mock_create.assert_not_called()

	def test_no_delivery_note_on_insert_even_if_closed(self):
		with patch(_DN_PATCH_TARGET) as mock_create:
			_make_warehouse_request(request_reason="Build Machine", status="Closed")
			mock_create.assert_not_called()
