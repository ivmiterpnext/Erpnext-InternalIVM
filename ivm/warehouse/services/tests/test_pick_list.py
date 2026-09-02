"""Integration tests for ivm.warehouse.services.pick_list"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

from ivm.warehouse.services.pick_list import (
    add_item_to_pick_list,
    clear_pick_list_items,
    create_pick_list,
    delete_draft_pick_list,
    remove_pick_list_item,
    serialize_pick_list,
    submit_pick_list,
    update_pick_list_item_qty,
)

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"


def _seed_stock(item_code, warehouse=WAREHOUSE, qty=100, rate=10):
    """Create stock via Material Receipt so Bin.actual_qty is populated."""
    se = make_stock_entry(
        item_code=item_code,
        qty=qty,
        basic_rate=rate,
        to_warehouse=warehouse,
        company=COMPANY,
        stock_entry_type="Material Receipt",
    )
    se.submit()


class TestCreatePickList(ERPNextTestSuite):
    """create_pick_list / delete_draft_pick_list"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure test company and warehouse exist
        if not frappe.db.exists("Company", "_Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "_Test Company",
                "abbr": "_TC",
                "country": "United States",
                "default_currency": "USD"
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Warehouse", "_Test Warehouse - _TC"):
            frappe.get_doc({
                "doctype": "Warehouse",
                "warehouse_name": "_Test Warehouse",
                "company": "_Test Company"
            }).insert(ignore_permissions=True)

    def test_create_returns_draft_name(self):
        name = create_pick_list(COMPANY)
        self.assertTrue(name)
        pl = frappe.get_doc("Pick List", name)
        self.assertEqual(pl.docstatus, 0)
        self.assertEqual(pl.company, COMPANY)
        self.assertEqual(pl.purpose, "Material Transfer")

    def test_delete_draft(self):
        name = create_pick_list(COMPANY)
        delete_draft_pick_list(name)
        self.assertFalse(frappe.db.exists("Pick List", name))

    def test_delete_submitted_raises(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 1)
        pl = frappe.get_doc("Pick List", name)
        pl.submit()
        with self.assertRaises(frappe.ValidationError):
            delete_draft_pick_list(name)


class TestAddItem(ERPNextTestSuite):
    """add_item_to_pick_list"""

    def test_add_new_item(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        result = add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        self.assertIn("row_name", result)
        self.assertEqual(result["qty"], 5)

    def test_add_increments_existing(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        r1 = add_item_to_pick_list(name, item.name, WAREHOUSE, 3)
        r2 = add_item_to_pick_list(name, item.name, WAREHOUSE, 2)
        self.assertEqual(r2["qty"], 5)
        self.assertEqual(r1["row_name"], r2["row_name"])

    def test_string_qty_coerced_to_float(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        result = add_item_to_pick_list(name, item.name, WAREHOUSE, "7")
        self.assertEqual(result["qty"], 7)

    def test_fetches_item_name_and_uom_when_omitted(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 1)
        pl = frappe.get_doc("Pick List", name)
        loc = pl.locations[0]
        self.assertTrue(loc.item_name)
        self.assertTrue(loc.uom)

    def test_add_to_submitted_pick_list_raises(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 1)
        frappe.get_doc("Pick List", name).submit()
        with self.assertRaises(frappe.ValidationError):
            add_item_to_pick_list(name, item.name, WAREHOUSE, 1)


class TestRemoveItem(ERPNextTestSuite):
    """remove_pick_list_item — including Priority 1 DoesNotExistError fix"""

    def test_remove_existing_row(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        r = add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        result = remove_pick_list_item(name, r["row_name"])
        self.assertTrue(result["success"])
        pl = frappe.get_doc("Pick List", name)
        self.assertEqual(len(pl.locations), 0)

    def test_remove_nonexistent_row_raises_does_not_exist(self):
        name = create_pick_list(COMPANY)
        with self.assertRaises(frappe.DoesNotExistError):
            remove_pick_list_item(name, "nonexistent-row-id")


class TestUpdateItemQty(ERPNextTestSuite):
    """update_pick_list_item_qty — including Priority 1 DoesNotExistError fix"""

    def test_update_qty(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        r = add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        update_pick_list_item_qty(name, r["row_name"], 10)
        pl = frappe.get_doc("Pick List", name)
        loc = pl.locations[0]
        self.assertEqual(loc.qty, 10)
        self.assertEqual(loc.picked_qty, 10)

    def test_update_with_string_qty(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        r = add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        update_pick_list_item_qty(name, r["row_name"], "3")
        pl = frappe.get_doc("Pick List", name)
        self.assertEqual(pl.locations[0].qty, 3)

    def test_update_nonexistent_row_raises_does_not_exist(self):
        name = create_pick_list(COMPANY)
        with self.assertRaises(frappe.DoesNotExistError):
            update_pick_list_item_qty(name, "nonexistent-row-id", 5)


class TestClearItems(ERPNextTestSuite):
    """clear_pick_list_items"""

    def test_clear_removes_all_rows(self):
        item_a = make_item()
        item_b = make_item()
        _seed_stock(item_a.name)
        _seed_stock(item_b.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item_a.name, WAREHOUSE, 3)
        add_item_to_pick_list(name, item_b.name, WAREHOUSE, 2)
        clear_pick_list_items(name)
        pl = frappe.get_doc("Pick List", name)
        self.assertEqual(len(pl.locations), 0)

    def test_clear_empty_pick_list_succeeds(self):
        name = create_pick_list(COMPANY)
        result = clear_pick_list_items(name)
        self.assertTrue(result["success"])


class TestSerializePickList(ERPNextTestSuite):
    """serialize_pick_list"""

    def test_draft_serialization_shape(self):
        item = make_item()
        _seed_stock(item.name, qty=50)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        pl = frappe.get_doc("Pick List", name)
        data = serialize_pick_list(pl)
        self.assertEqual(data["pick_list"], name)
        self.assertFalse(data["submitted"])
        self.assertIsNone(data["stock_entry"])
        self.assertEqual(len(data["items"]), 1)
        row = data["items"][0]
        self.assertEqual(row["item_code"], item.name)
        self.assertEqual(row["qty"], 5)
        self.assertEqual(row["available_qty"], 50)
        self.assertIn("row_name", row)
        self.assertIn("uom", row)

    def test_draft_available_qty_is_live(self):
        """Draft serialization should query current Bin qty, not stale stock_qty."""
        item = make_item()
        _seed_stock(item.name, qty=20)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        # Add more stock after the pick list row was created
        _seed_stock(item.name, qty=30)
        pl = frappe.get_doc("Pick List", name)
        data = serialize_pick_list(pl)
        self.assertEqual(data["items"][0]["available_qty"], 50)


class TestSubmitPickList(ERPNextTestSuite):
    """submit_pick_list"""

    def test_submit_creates_stock_entry(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        result = submit_pick_list(name, target_warehouse=WAREHOUSE)
        self.assertIn("stock_entry", result)
        self.assertTrue(result["stock_entry"])
        se = frappe.get_doc("Stock Entry", result["stock_entry"])
        self.assertEqual(se.docstatus, 0)  # draft Stock Entry

    def test_submit_with_target_warehouse(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        target = "_Test Warehouse 1 - _TC"
        result = submit_pick_list(name, target_warehouse=target)
        se = frappe.get_doc("Stock Entry", result["stock_entry"])
        for row in se.items:
            self.assertEqual(row.t_warehouse, target)

    def test_submit_without_target_warehouse_raises(self):
        """A Pick List with no parent_warehouse and no target_warehouse arg
        should fail at the Stock Entry validation layer, since there is no
        destination warehouse for the transfer."""
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        with self.assertRaises(frappe.ValidationError):
            submit_pick_list(name)

    def test_submit_links_warehouse_request(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        # Create a Warehouse Request pointing at this Pick List
        wr = frappe.get_doc({
            "doctype": "Warehouse Request",
            "pick_list": name,
            "request_reason": "Build Machine",
            "subject": "Test WR",
        })
        wr.insert(ignore_permissions=True)
        result = submit_pick_list(name, target_warehouse=WAREHOUSE)
        se = frappe.get_doc("Stock Entry", result["stock_entry"])
        self.assertEqual(se.custom_warehouse_request, wr.name)

    def test_submit_already_submitted_raises(self):
        item = make_item()
        _seed_stock(item.name)
        name = create_pick_list(COMPANY)
        add_item_to_pick_list(name, item.name, WAREHOUSE, 5)
        frappe.get_doc("Pick List", name).submit()
        with self.assertRaises(frappe.ValidationError):
            submit_pick_list(name)
