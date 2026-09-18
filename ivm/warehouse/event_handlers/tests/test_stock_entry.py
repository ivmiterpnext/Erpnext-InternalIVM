"""Integration tests for ivm.warehouse.event_handlers.stock_entry"""

from unittest.mock import patch, call
import frappe
from erpnext.tests.utils import ERPNextTestSuite
from erpnext.stock.doctype.item.test_item import make_item
from erpnext.stock.doctype.stock_entry.stock_entry_utils import make_stock_entry

COMPANY = "_Test Company"
WAREHOUSE = "_Test Warehouse - _TC"
TARGET_WAREHOUSE = "_Test Warehouse 1 - _TC"

# Counter for unique Stock Entry names
_se_counter = 0


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
    global _se_counter
    _se_counter += 1
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "name": f"MAT-STE-TEST-{_se_counter}",
        "stock_entry_type": "Material Transfer",
        "company": COMPANY,
        "from_warehouse": WAREHOUSE,
        "to_warehouse": TARGET_WAREHOUSE,
        "posting_date": frappe.utils.today(),
        "items": [{
            "item_code": item_code,
            "qty": qty,
            "basic_rate": rate,
            "s_warehouse": WAREHOUSE,
            "t_warehouse": TARGET_WAREHOUSE,
        }],
        "custom_warehouse_request": wr_name,
    })
    if submit:
        se.insert(ignore_permissions=True)
        se.submit()
    else:
        se.insert(ignore_permissions=True)
    return se


def _make_stock_entry(item_code, qty, stock_entry_type="Material Transfer", wr_name=None, rate=10):
    """Create a Stock Entry with unique name."""
    global _se_counter
    _se_counter += 1
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "name": f"SE-TEST-{_se_counter}",
        "stock_entry_type": stock_entry_type,
        "company": COMPANY,
        "from_warehouse": WAREHOUSE,
        "to_warehouse": TARGET_WAREHOUSE,
        "posting_date": frappe.utils.today(),
        "items": [{
            "item_code": item_code,
            "qty": qty,
            "basic_rate": rate,
            "s_warehouse": WAREHOUSE,
            "t_warehouse": TARGET_WAREHOUSE,
        }],
    })
    if wr_name:
        se.custom_warehouse_request = wr_name
    se.insert(ignore_permissions=True)
    return se


def _make_user_with_role(email, first_name, role_name):
    """Create a User with a given role."""
    user_doc = frappe.get_doc({
        "doctype": "User",
        "email": email,
        "first_name": first_name,
        "send_welcome_email": 0,
    })
    user_doc.insert(ignore_permissions=True)
    user_doc.add_roles(role_name)
    return user_doc


class TestAfterInsert(ERPNextTestSuite):
    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_wrong_stock_entry_type_not_called(self, mock_enqueue):
        """stock_entry_type != 'Material Transfer' → not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        _make_stock_entry(item.name, 5, stock_entry_type="Material Issue", wr_name=wr.name)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_no_custom_warehouse_request_not_called(self, mock_enqueue):
        """No custom_warehouse_request → not called."""
        item = make_item()
        _seed_stock(item.name)
        
        _make_stock_entry(item.name, 5)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_invalid_request_reason_not_called(self, mock_enqueue):
        """WR request_reason = 'Other' (not Shipping Request, not Build-prefixed) → not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Other")
        
        _make_stock_entry(item.name, 5, wr_name=wr.name)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_no_stock_managers_not_called(self, mock_enqueue):
        """No users with Stock Manager role exist → not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        _make_stock_entry(item.name, 5, wr_name=wr.name)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_only_disabled_stock_manager_not_called(self, mock_enqueue):
        """Stock Manager role user exists but is disabled → excluded, not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        # Create disabled Stock Manager
        user = _make_user_with_role("disabled_manager@test.com", "Disabled", "Stock Manager")
        user.enabled = 0
        user.save(ignore_permissions=True)
        
        _make_stock_entry(item.name, 5, wr_name=wr.name)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_current_session_user_excluded(self, mock_enqueue):
        """Stock Manager is current session user → excluded, not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        # Current session user is "Administrator" in tests
        # Add Stock Manager role to Administrator (if not already present)
        admin_user = frappe.get_doc("User", frappe.session.user)
        if "Stock Manager" not in [r.role for r in admin_user.roles]:
            admin_user.add_roles("Stock Manager")
        
        _make_material_transfer(wr.name, item.name, 5, submit=False)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_shipping_request_calls_with_enabled_manager(self, mock_enqueue):
        """Valid case: enabled Stock Manager + Shipping Request → called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        # Create enabled Stock Manager (not Administrator)
        manager = _make_user_with_role("manager@test.com", "Manager", "Stock Manager")
        
        se = _make_material_transfer(wr.name, item.name, 5, submit=False)
        
        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        recipients, notification_doc = call_args[0]
        
        self.assertIn(manager.name, recipients)
        self.assertEqual(notification_doc["document_type"], "Stock Entry")
        self.assertEqual(notification_doc["document_name"], se.name)

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_build_request_calls_with_enabled_manager(self, mock_enqueue):
        """Valid case: enabled Stock Manager + Build-prefixed reason → called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Build Machine")
        
        # Create enabled Stock Manager (not Administrator)
        manager = _make_user_with_role("manager2@test.com", "Manager2", "Stock Manager")
        
        se = _make_material_transfer(wr.name, item.name, 5, submit=False)
        
        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        recipients, notification_doc = call_args[0]
        
        self.assertIn(manager.name, recipients)
        self.assertEqual(notification_doc["document_type"], "Stock Entry")
        self.assertEqual(notification_doc["document_name"], se.name)


class TestOnSubmit(ERPNextTestSuite):
    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_wrong_stock_entry_type_not_called(self, mock_enqueue):
        """stock_entry_type != 'Material Transfer' → not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        _make_stock_entry(item.name, 5, stock_entry_type="Material Issue", wr_name=wr.name)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_invalid_request_reason_not_called(self, mock_enqueue):
        """WR request_reason invalid → not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Other")
        
        _make_material_transfer(wr.name, item.name, 5, submit=True)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_no_todo_assignees_not_called(self, mock_enqueue):
        """No ToDo assignees for the WR → not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        _make_material_transfer(wr.name, item.name, 5, submit=True)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_cancelled_todo_excluded_not_called(self, mock_enqueue):
        """ToDo exists but status='Cancelled' → excluded, not called."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        # Create a cancelled ToDo
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "reference_type": "Warehouse Request",
            "reference_name": wr.name,
            "status": "Cancelled",
            "allocated_to": "Administrator",
            "description": "Test ToDo",
        })
        todo.insert(ignore_permissions=True)
        
        _make_material_transfer(wr.name, item.name, 5, submit=True)
        
        mock_enqueue.assert_not_called()

    @patch("ivm.warehouse.event_handlers.stock_entry.enqueue_create_notification")
    def test_open_todo_calls_with_assignee(self, mock_enqueue):
        """ToDo with status='Open' → called with assignee."""
        item = make_item()
        _seed_stock(item.name)
        wr = _make_warehouse_request(request_reason="Shipping Request")
        
        # Create an open ToDo
        assignee_user = frappe.get_doc({
            "doctype": "User",
            "email": "assignee@test.com",
            "first_name": "Assignee",
            "send_welcome_email": 0,
        }).insert(ignore_permissions=True)
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "reference_type": "Warehouse Request",
            "reference_name": wr.name,
            "status": "Open",
            "allocated_to": assignee_user.name,
            "description": "Test ToDo",
        })
        todo.insert(ignore_permissions=True)
        
        _make_material_transfer(wr.name, item.name, 5, submit=True)
        
        mock_enqueue.assert_called_once()
        call_args = mock_enqueue.call_args
        recipients, notification_doc = call_args[0]
        
        self.assertIn(assignee_user.name, recipients)
        self.assertEqual(notification_doc["document_type"], "Warehouse Request")
        self.assertEqual(notification_doc["document_name"], wr.name)
