"""One-off cleanup: collapse duplicate `is_primary` flags on Contact Email
and Contact Phone child rows left over from historical Contact-merge
operations (e.g. legacy pre-HubSpot Contacts merged with HubSpot-created
duplicates via frappe.rename_doc(merge=True), which concatenates child
table rows without deduplicating primary flags). Contact.set_primary_email()
/ set_primary() then reject the next save on any such Contact.

NOT registered in patches.txt — this is a manual, one-time data-fix
operation, not something that should silently re-run on every bench
migrate. The forward-looking fix (self-healing normalization on every
HubSpot sync) lives in contact_handler.py; this patch only cleans up the
existing backlog.

Run manually, dry-run first (default):
    bench --site <site> execute \\
        "ivm.integrations.hubspot.patches.fix_duplicate_primary_contact_fields.execute" \\
        --kwargs '{"dry_run": true}'

Review the printed dry-run output above, then apply:
    bench --site <site> execute \\
        "ivm.integrations.hubspot.patches.fix_duplicate_primary_contact_fields.execute" \\
        --kwargs '{"dry_run": false}'

Idempotent — re-running after a clean pass finds zero affected groups.
"""

from __future__ import annotations

import json

import frappe

_FIELD_TRIPLES = [
    ("Contact Email", "is_primary", "email_id", "email_id"),
    ("Contact Phone", "is_primary_phone", "phone", "phone"),
    ("Contact Phone", "is_primary_mobile_no", "phone", "mobile_no"),
]


def execute(dry_run: bool = True) -> None:
    for child_table, primary_field, value_field, flat_field in _FIELD_TRIPLES:
        _fix_field(child_table, primary_field, value_field, flat_field, dry_run)


def _fix_field(
    child_table: str,
    primary_field: str,
    value_field: str,
    flat_field: str,
    dry_run: bool,
) -> None:
    groups = frappe.db.sql(
        f"""
        SELECT parent FROM `tab{child_table}`
        WHERE `{primary_field}` = 1
        GROUP BY parent
        HAVING COUNT(*) > 1
        """,
        as_dict=True,
    )
    parents = [g["parent"] for g in groups]
    print(f"{child_table}.{primary_field}: {len(parents)} affected Contact(s).")

    if not parents:
        return

    fixed = 0

    for parent in parents:
        rows = frappe.db.sql(
            f"""
            SELECT name, `{value_field}` AS value, `{primary_field}` AS is_primary, idx
            FROM `tab{child_table}`
            WHERE parent = %s
            ORDER BY idx
            """,
            (parent,),
            as_dict=True,
        )
        flat_value = frappe.db.get_value("Contact", parent, flat_field)

        flat_matches = [r for r in rows if flat_value and r["value"] == flat_value]
        if len(flat_matches) == 1:
            winner = flat_matches[0]
            reason = "flat_field_match"
        else:
            primary_rows = [r for r in rows if r["is_primary"]]
            winner = min(primary_rows, key=lambda r: r["idx"]) if primary_rows else rows[0]
            reason = "fallback_lowest_idx"

        print(json.dumps({
            "parent": parent,
            "rows": rows,
            "flat_value": flat_value,
            "winner": winner["name"],
            "reason": reason,
        }))

        if not dry_run:
            other_names = [r["name"] for r in rows if r["name"] != winner["name"]]
            if other_names:
                placeholders = ", ".join(["%s"] * len(other_names))
                frappe.db.sql(
                    f"""
                    UPDATE `tab{child_table}` SET `{primary_field}` = 0
                    WHERE name IN ({placeholders})
                    """,
                    tuple(other_names),
                )
            frappe.db.sql(
                f"""
                UPDATE `tab{child_table}` SET `{primary_field}` = 1
                WHERE name = %s
                """,
                (winner["name"],),
            )
        fixed += 1

    if not dry_run:
        frappe.db.commit()
        print(f"  Fixed {fixed} group(s).")
    else:
        print(f"  DRY RUN - {fixed} group(s) would be fixed. No changes made.")
