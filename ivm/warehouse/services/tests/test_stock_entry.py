"""Integration tests for ivm.warehouse.services.stock_entry"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from ivm.warehouse.services.stock_entry import get_stock_entry_items_from_warehouse_request

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
TARGET_WAREHOUSE = "_Test Warehouse 1 - _TC"


def _make_warehouse_request(**kwargs):
    doc = frappe.get_doc({
        "doctype": "Warehouse Request",
        "request_reason": kwargs.get("request_reason", "Shipping Request"),
        "subject": kwargs.get("subject", "Test WR"),
        "status": kwargs.get("status", "New"),
    })
    doc.insert(ignore_permissions=True)
    return doc


def _seed_stock(item_code, qty=100, rate=10):
    se = make_stock_entry(
        item_code=item_code, qty=qty, basic_rate=rate,
        to_warehouse=WAREHOUSE, company=COMPANY,
        stock_entry_type="Material Receipt",
    )
    se.submit()


def _make_material_transfer(wr_name, item_code, qty, rate=10, submit=True):
    se = make_stock_entry(
        item_code=item_code, qty=qty, basic_rate=rate,
        from_warehouse=WAREHOUSE, to_warehouse=TARGET_WAREHOUSE,
        company=COMPANY, stock_entry_type="Material Transfer",
        do_not_submit=True,
    )
    se.custom_warehouse_request = wr_name
    if submit:
        se.submit()
    else:
        se.save(ignore_permissions=True)
    return se


class TestGetStockEntryItemsFromWarehouseRequest(ERPNextTestSuite):
    def test_no_entries_returns_empty_list(self):
        wr = _make_warehouse_request()
        self.assertEqual(get_stock_entry_items_from_warehouse_request(wr.name), [])

    def test_draft_entries_excluded(self):
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request()
        _make_material_transfer(wr.name, item.name, 5, submit=False)
        self.assertEqual(get_stock_entry_items_from_warehouse_request(wr.name), [])

    def test_returns_submitted_entry_items(self):
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request()
        _make_material_transfer(wr.name, item.name, 5)

        result = get_stock_entry_items_from_warehouse_request(wr.name)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_code"], item.name)
        self.assertEqual(result[0]["qty"], 5)
        self.assertEqual(result[0]["warehouse"], TARGET_WAREHOUSE)

    def test_quantities_summed_across_multiple_entries_same_item_warehouse(self):
        item = make_item()
        _seed_stock(item.name, qty=200)
        wr = _make_warehouse_request()
        _make_material_transfer(wr.name, item.name, 5)
        _make_material_transfer(wr.name, item.name, 3)

        result = get_stock_entry_items_from_warehouse_request(wr.name)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["qty"], 8)

    def test_different_items_produce_separate_rows(self):
        item_a = make_item()
        item_b = make_item()
        _seed_stock(item_a.name)
        _seed_stock(item_b.name)
        wr = _make_warehouse_request()
        _make_material_transfer(wr.name, item_a.name, 2)
        _make_material_transfer(wr.name, item_b.name, 4)

        result = get_stock_entry_items_from_warehouse_request(wr.name)
        self.assertEqual(len(result), 2)
