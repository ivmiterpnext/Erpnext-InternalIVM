
import frappe
from frappe.model.document import Document

MAX_RFID_SETTINGS_ROWS = 5


class WarehouseRequest(Document):
    def validate(self):
        if len(self.rfid_settings or []) > MAX_RFID_SETTINGS_ROWS:
            frappe.throw(
                f"You can only add up to {MAX_RFID_SETTINGS_ROWS} RFID Settings rows."
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
