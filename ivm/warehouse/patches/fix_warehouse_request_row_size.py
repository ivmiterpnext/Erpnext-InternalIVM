"""Drop orphan columns from tabWarehouse Request to fix row size limit.

The table has accumulated 9 varchar(140) columns that have no corresponding
field definition in the DocType JSON or custom_field fixtures. Each consumes
~562 bytes of row space (140 chars * 4 bytes/char for utf8mb4 + 2 bytes
length prefix), totalling ~5,058 bytes of dead weight that pushes the table
over MariaDB's 65,535-byte InnoDB row size limit.

These columns appear to be remnants of old migrations, experiments, or
renamed fields that were never cleaned up at the database level.
"""

import frappe


ORPHAN_COLUMNS = [
    "warehouse_request_name",
    "rasied_by",
    "raised_by",
    "machine_number_1",
    "1_machine_number_1",
    "_1_mac_address",
    "testprose1",
    "imported_equipment_numbers",
    "number_4_task_sent",
]


def execute():
    # Get actual columns in the table to avoid ALTER errors on missing columns
    existing_columns = {
        row[0]
        for row in frappe.db.sql(
            """SELECT COLUMN_NAME FROM information_schema.COLUMNS
               WHERE TABLE_NAME = 'tabWarehouse Request'
               AND TABLE_SCHEMA = DATABASE()"""
        )
    }

    columns_to_drop = [c for c in ORPHAN_COLUMNS if c in existing_columns]

    if not columns_to_drop:
        print("No orphan columns found — nothing to do.")
        return

    drop_clauses = ", ".join(f"DROP COLUMN `{c}`" for c in columns_to_drop)
    query = f"ALTER TABLE `tabWarehouse Request` {drop_clauses}"

    print(f"Dropping {len(columns_to_drop)} orphan columns: {columns_to_drop}")
    frappe.db.sql_ddl(query)
    print("Done.")
