# Copyright (c) 2023, korecent and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WarehouseRequest(Document):
    def get_title(self):
        """Return formatted title for link fields"""
        if self.subject:
            return f"{self.name} - {self.subject}"
        return self.name

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
