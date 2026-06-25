"""
A Deployment Location represents a physical site linked to a CRM Deal,
containing site-level information and one or more machine child tables 
(SmartStation, SmartLocker, SmartSync, SmartVault, SmartCenter).
"""

import frappe
from frappe.model.document import Document
from ivm.deals.constants import TABLE_LABELS, TABLE_TO_QUANTITY
from ivm.integrations.hubspot.sync_utils import coerce_value


class DeploymentLocation(Document):

    def validate(self) -> None:
        """Run all validation and auto-calculation hooks before save."""

        self._sanitise_child_select_fields()
        self._update_device_quantities()
        self._validate_unique_machine_names()

    def _sanitise_child_select_fields(self) -> None:
        """Coerce invalid Select values on child table rows before Frappe validates them."""

        for table_field in TABLE_TO_QUANTITY:
            rows = self.get(table_field) or []
            if not rows:
                continue

            meta = frappe.get_meta(rows[0].doctype)
            select_fields = [df for df in meta.fields if df.fieldtype == "Select"]
            if not select_fields:
                continue

            for row in rows:
                for df in select_fields:
                    value = row.get(df.fieldname)
                    if value is None or value == "":
                        continue

                    coerced = coerce_value(value, df)
                    if coerced != value:
                        row.set(df.fieldname, coerced)

    def _update_device_quantities(self) -> None:
        """Keep the read-only quantity fields in sync with child table row counts."""

        for table_field, qty_field in TABLE_TO_QUANTITY.items():
            self.set(qty_field, len(self.get(table_field) or []))

    def _validate_unique_machine_names(self) -> None:
        """Ensure ``machine_name`` is unique within each child table."""

        for table_field in TABLE_TO_QUANTITY:
            label = TABLE_LABELS.get(table_field, table_field)
            seen: dict[str, int] = {}

            for row in self.get(table_field) or []:
                name = row.get("machine_name")

                if not name:
                    continue

                if name in seen:
                    frappe.throw(
                        f"Duplicate machine name <b>{name}</b> in {label} Details "
                        f"(rows {seen[name]} and {row.idx})."
                    )

                seen[name] = row.idx
