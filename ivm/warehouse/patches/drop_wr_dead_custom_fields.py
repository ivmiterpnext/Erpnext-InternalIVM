"""
Drop dead Custom Fields (and their orphaned columns) from Warehouse Request.

Warehouse Request is a fully custom, app-owned DocType — it should never
have needed the Custom Field mechanism at all (that mechanism exists to
extend DocTypes you don't own the source of). These accumulated via ad-hoc
Customize Form usage over time. Each was checked for code/report/workflow
references and real data recency before being marked dead:

- time_spent: 0/11,065 records populated, zero code references.
- new_request: Read Only, every single record holds the literal constant
  "new" — zero variance, zero information, zero code references.
- bonus_timestamp: only 2% populated, no new values written since mid-2025.
  Its sole writer (the "Warehouse Bonus Time Stamp" Client Script, deleted
  separately) checked a field ("bonus_requirement_met") that does not exist
  anywhere on this DocType — the trigger was permanently dead code. Its two
  report consumers ("Quarterly Metrics", "Warehouse 24 metrics") confirmed
  no longer in use.
- explanation: 1% populated, stale since mid-2025, zero code references.
- number_of_devices: 2.7% populated, stale since 2023, zero code references.
- time_due: 97% populated but zero code/report consumer found anywhere;
  no automation reads it.
- use_existing_plan: 3% populated, all values written during the initial
  2023 data migration window and never touched since, zero code references.
- section_break_csbpl: pure layout element, no longer needed.
- owner_name: 97% populated, but its only real consumers — the "Open
  Warehouse Requests" and "Warehouse Requests Closed This Month" reports,
  and the three dashboard charts built on/around them — were all confirmed
  unused (untouched since 2023-09-25, none placed on any workspace). One of
  the two reports was found actively broken, referencing a column
  ("warehouse_request_name") that never existed as a real DB column — a
  stale artifact of a client-side-only JS assignment in the
  "Warehouse Request Naming" Client Script that was never persisted. Both
  reports and all three charts have been deleted (DB records + their
  module-standard source folders). With its consumers gone, owner_name
  itself has no remaining reason to exist.

Removed from the custom_field fixture (for the fields that were ever Custom
Fields) and from the DocType JSON's own fields/field_order (for owner_name,
which had briefly been folded into the native schema before its consumers
were found to be dead too). This patch deletes the leftover DB records and
drops the leftover DB columns (fixture sync never deletes records absent
from the JSON, and schema sync never drops orphaned columns, so both must
be explicit).

Safe to run repeatedly (idempotent).
"""

import frappe


FIELDS_WITH_COLUMNS = [
    "time_spent",
    "new_request",
    "bonus_timestamp",
    "explanation",
    "number_of_devices",
    "time_due",
    "use_existing_plan",
    "owner_name",
]

FIELDS_WITHOUT_COLUMNS = [
    "section_break_csbpl",
]


def execute():
    for fieldname in FIELDS_WITH_COLUMNS + FIELDS_WITHOUT_COLUMNS:
        custom_field_name = f"Warehouse Request-{fieldname}"
        if frappe.db.exists("Custom Field", custom_field_name):
            frappe.delete_doc("Custom Field", custom_field_name, ignore_permissions=True, force=True)
            print(f"  Deleted Custom Field: {custom_field_name}")
        else:
            print(f"  Custom Field {custom_field_name} does not exist — skipping")

    frappe.db.commit()
    existing_columns = {
        row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabWarehouse Request`")
    }
    for fieldname in FIELDS_WITH_COLUMNS:
        if fieldname in existing_columns:
            frappe.db.sql_ddl(f"ALTER TABLE `tabWarehouse Request` DROP COLUMN `{fieldname}`")
            print(f"  Dropped column tabWarehouse Request.{fieldname}")
        else:
            print(f"  tabWarehouse Request.{fieldname} does not exist — skipping")

    # Also clean up the "Open Warehouse Requests" / "Warehouse Requests
    # Closed This Month" reports and dashboard charts that depended on
    # owner_name — deleted from source (report/dashboard_chart module
    # folders removed from the app); this drops the leftover DB records
    # for sites that already migrated the standard docs in before removal.
    for report_name in ["Open Warehouse Requests", "Warehouse Requests Closed This Month"]:
        if frappe.db.exists("Report", report_name):
            frappe.delete_doc("Report", report_name, ignore_permissions=True, force=True)
            print(f"  Deleted Report: {report_name}")
        else:
            print(f"  Report {report_name} does not exist — skipping")

    for chart_name in ["Open Warehouse Request", "Warehouse Requests Closed This Month", "Open Warehouse Requests"]:
        if frappe.db.exists("Dashboard Chart", chart_name):
            frappe.delete_doc("Dashboard Chart", chart_name, ignore_permissions=True, force=True)
            print(f"  Deleted Dashboard Chart: {chart_name}")
        else:
            print(f"  Dashboard Chart {chart_name} does not exist — skipping")

    frappe.clear_cache(doctype="Warehouse Request")
