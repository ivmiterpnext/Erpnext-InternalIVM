"""Integration tests for ivm.warehouse.services.inventory"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from ivm.warehouse.services.inventory import (
    get_available_qty,
    get_item_with_warehouse,
    search_items_by_name,
    _get_leaf_warehouses,
    _get_top_level_warehouse_map,
)

COMPANY = "_Test Company"
GROUP_WAREHOUSE = "All Warehouses - _TC"
LEAF_WH_1 = "Stores - _TC"
LEAF_WH_2 = "Finished Goods - _TC"
SMALL_GROUP = "_Test Warehouse Group - _TC"
SMALL_GROUP_C1 = "_Test Warehouse Group-C1 - _TC"
SMALL_GROUP_C2 = "_Test Warehouse Group-C2 - _TC"


def _seed_stock(item_code, warehouse=LEAF_WH_1, qty=100, rate=10):
    """Create stock via Material Receipt so Bin.actual_qty is populated."""
    make_stock_entry(
        item_code=item_code,
        qty=qty,
        basic_rate=rate,
        to_warehouse=warehouse,
        company=COMPANY,
        stock_entry_type="Material Receipt",
    )


class TestGetAvailableQty(ERPNextTestSuite):

    def test_returns_qty_when_stock_exists(self):
        item = make_item()
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=50)
        self.assertEqual(get_available_qty(item.name, LEAF_WH_1), 50)

    def test_returns_zero_when_no_bin(self):
        item = make_item()
        self.assertEqual(get_available_qty(item.name, LEAF_WH_1), 0)

    def test_returns_zero_for_different_warehouse(self):
        item = make_item()
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=50)
        self.assertEqual(get_available_qty(item.name, LEAF_WH_2), 0)


class TestGetLeafWarehouses(ERPNextTestSuite):

    def test_leaf_input_returns_itself(self):
        result = _get_leaf_warehouses(LEAF_WH_1)
        self.assertEqual(result, [LEAF_WH_1])

    def test_group_returns_all_leaf_children(self):
        result = _get_leaf_warehouses(GROUP_WAREHOUSE)
        expected = {"Stores - _TC", "Work In Progress - _TC", "Finished Goods - _TC", "Goods In Transit - _TC"}
        self.assertEqual(set(result), expected)

    def test_small_group_returns_exact_children(self):
        result = _get_leaf_warehouses(SMALL_GROUP)
        self.assertCountEqual(result, [SMALL_GROUP_C1, SMALL_GROUP_C2])


class TestGetTopLevelWarehouseMap(ERPNextTestSuite):

    def test_empty_list_returns_empty_dict(self):
        self.assertEqual(_get_top_level_warehouse_map([]), {})

    def test_direct_children_of_root_map_to_themselves(self):
        result = _get_top_level_warehouse_map(["Stores - _TC", "Finished Goods - _TC"])
        self.assertEqual(result["Stores - _TC"], "Stores - _TC")
        self.assertEqual(result["Finished Goods - _TC"], "Finished Goods - _TC")

    def test_small_group_children_map_to_themselves(self):
        result = _get_top_level_warehouse_map([SMALL_GROUP_C1])
        self.assertEqual(result[SMALL_GROUP_C1], SMALL_GROUP_C1)


class TestGetItemWithWarehouse(ERPNextTestSuite):

    def test_nonexistent_item_raises(self):
        with self.assertRaises(frappe.DoesNotExistError):
            get_item_with_warehouse("ITEM-DOES-NOT-EXIST-999", parent_warehouse=GROUP_WAREHOUSE)

    def test_item_with_no_stock_returns_empty_warehouses(self):
        item = make_item()
        result = get_item_with_warehouse(item.name, parent_warehouse=GROUP_WAREHOUSE)
        self.assertEqual(result["item_code"], item.name)
        self.assertTrue(result["item_name"])
        self.assertTrue(result["stock_uom"])
        self.assertEqual(result["warehouses"], [])

    def test_returns_warehouses_sorted_by_qty_desc(self):
        item = make_item()
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=30)
        _seed_stock(item.name, warehouse=LEAF_WH_2, qty=50)
        result = get_item_with_warehouse(item.name, parent_warehouse=GROUP_WAREHOUSE)
        whs = result["warehouses"]
        self.assertEqual(len(whs), 2)
        self.assertEqual(whs[0]["warehouse"], LEAF_WH_2)
        self.assertEqual(whs[0]["available_qty"], 50)
        self.assertEqual(whs[1]["warehouse"], LEAF_WH_1)
        self.assertEqual(whs[1]["available_qty"], 30)

    def test_excludes_zero_stock_warehouses(self):
        item = make_item()
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=10)
        result = get_item_with_warehouse(item.name, parent_warehouse=GROUP_WAREHOUSE)
        warehouse_names = [w["warehouse"] for w in result["warehouses"]]
        self.assertIn(LEAF_WH_1, warehouse_names)
        self.assertNotIn(LEAF_WH_2, warehouse_names)

    def test_top_level_warehouse_populated(self):
        item = make_item()
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=10)
        result = get_item_with_warehouse(item.name, parent_warehouse=GROUP_WAREHOUSE)
        self.assertEqual(result["warehouses"][0]["top_level_warehouse"], "Stores - _TC")


class TestSearchItemsByName(ERPNextTestSuite):

    def test_short_text_returns_empty(self):
        self.assertEqual(search_items_by_name("A", parent_warehouse=GROUP_WAREHOUSE), [])

    def test_empty_text_returns_empty(self):
        self.assertEqual(search_items_by_name("", parent_warehouse=GROUP_WAREHOUSE), [])

    def test_finds_item_by_partial_name(self):
        item = make_item(properties={"item_name": "Hydraulic Pump XYZ123"})
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=25)
        results = search_items_by_name("Hydraulic", parent_warehouse=GROUP_WAREHOUSE)
        codes = [r["item_code"] for r in results]
        self.assertIn(item.name, codes)

    def test_no_match_returns_empty(self):
        item = make_item()
        _seed_stock(item.name, warehouse=LEAF_WH_1, qty=10)
        results = search_items_by_name("ZZZNONEXISTENT99", parent_warehouse=GROUP_WAREHOUSE)
        self.assertEqual(results, [])

    def test_limit_restricts_result_count(self):
        items = [make_item(properties={"item_name": f"LimitTestPart {i}"}) for i in range(3)]
        for it in items:
            _seed_stock(it.name, warehouse=LEAF_WH_1, qty=10)
        results = search_items_by_name("LimitTestPart", parent_warehouse=GROUP_WAREHOUSE, limit=1)
        self.assertEqual(len(results), 1)
