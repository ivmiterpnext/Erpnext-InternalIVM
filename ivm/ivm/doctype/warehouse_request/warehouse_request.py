
import frappe
from frappe.model.document import Document

MAX_RFID_SETTINGS_ROWS = 5


class WarehouseRequest(Document):
    def validate(self):
        self._validate_rfid_settings()
        self._validate_crated_status()
        self._validate_closed_status()

    def _validate_rfid_settings(self):
        if len(self.rfid_settings or []) > MAX_RFID_SETTINGS_ROWS:
            frappe.throw(
                f"You can only add up to {MAX_RFID_SETTINGS_ROWS} RFID Settings rows."
            )

    def _validate_crated_status(self):
        if self.status != "Crated - Ready to Ship":
            return
        if not self.request_reason or not self.request_reason.startswith("Build"):
            return

        if not self.pick_list:
            frappe.throw(
                "Cannot set status to 'Crated - Ready to Ship' without a Pick List. "
                "Please complete the picking process first."
            )

        stock_entry = frappe.db.get_value(
            "Stock Entry",
            {"pick_list": self.pick_list, "docstatus": ["!=", 2]},
            ["name", "docstatus"],
            as_dict=True,
        )

        if not stock_entry:
            frappe.throw(
                "Cannot set status to 'Crated - Ready to Ship' — no Stock Entry "
                "exists for this Build's Pick List."
            )

        if stock_entry.docstatus != 1:
            frappe.throw(
                "Cannot set status to 'Crated - Ready to Ship' — Stock Entry "
                f'<a href="/app/stock-entry/{stock_entry.name}">{stock_entry.name}</a> '
                "is still in draft. Please submit it first so "
                "that items are transferred to the WIP warehouse."
            )

    def _validate_closed_status(self):
        if self.status != "Closed":
            return
        if self.request_reason != "Shipping Request":
            return

        if not self.pick_list:
            frappe.throw(
                "Cannot close this Shipping Request without a Pick List. "
                "Please complete the picking process first."
            )

        stock_entry = frappe.db.get_value(
            "Stock Entry",
            {"custom_warehouse_request": self.name, "docstatus": ["!=", 2]},
            ["name", "docstatus"],
            as_dict=True,
        )

        if not stock_entry:
            frappe.throw(
                "Cannot close this Shipping Request — no Stock Entry (Material Transfer) "
                "is linked to it. Please submit the material transfer first."
            )

        if stock_entry.docstatus != 1:
            frappe.throw(
                "Cannot close this Shipping Request — Stock Entry "
                f'<a href="/app/stock-entry/{stock_entry.name}">{stock_entry.name}</a> '
                "is still in draft. Please submit it first."
            )

    def on_update(self):
        old_doc = self.get_doc_before_save()
        if not old_doc:
            return

        status_changed_to_closed = (
            old_doc.status != "Closed" and self.status == "Closed"
        )
        if status_changed_to_closed and self.request_reason == "Shipping Request":
            from ivm.warehouse.services.delivery_note import (create_delivery_note_from_warehouse_request)

            create_delivery_note_from_warehouse_request(self.name)
