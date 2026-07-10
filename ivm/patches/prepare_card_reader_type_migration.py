"""
Data prep for converting card_reader_type fields to Link against the new
Card Reader Type master doctype.

1. Removes a duplicate Custom Field record that was mistakenly created on
   Warehouse Request for card_reader_type, shadowing the doctype's own
   native field definition.
2. Removes the Project.card_reader_type Custom Field entirely. It has been
   dropped from ivm/ivm/custom/project.json since it's unused by any code
   path, but Frappe's customization sync only adds/updates fields from
   those files — it never deletes ones that were removed, so this has to
   be done explicitly.
3. Blanks out the literal string "--None--" on Issue.card_reader_type
   (85k+ legacy records) since blank is now the equivalent "no selection"
   state for the new Link field, and "--None--" is not being carried
   forward as a master data value.
4. Deletes the orphaned Project Card Reader Type child table doctype.
   It was a free-text child table on Project (unused, 0 rows, no
   remaining references anywhere in the app). Its doctype folder has
   been removed from source; Frappe's sync never deletes existing
   DocType records just because the source folder disappeared, so the
   DocType record (and its backing table) must be dropped explicitly.
"""

import frappe


def execute():
    existing = frappe.db.get_value(
        "Custom Field",
        {"dt": "Warehouse Request", "fieldname": "card_reader_type"},
        "name",
    )
    if existing:
        frappe.delete_doc("Custom Field", existing, ignore_permissions=True)
        print(f"  Deleted duplicate Custom Field '{existing}' on Warehouse Request.card_reader_type")
    else:
        print("  No duplicate Custom Field found on Warehouse Request.card_reader_type — skipping")

    existing = frappe.db.get_value(
        "Custom Field",
        {"dt": "Project", "fieldname": "card_reader_type"},
        "name",
    )
    if existing:
        frappe.delete_doc("Custom Field", existing, ignore_permissions=True)
        print(f"  Deleted removed Custom Field '{existing}' on Project.card_reader_type")
    else:
        print("  No Custom Field found on Project.card_reader_type — skipping")

    affected = frappe.db.count("Issue", filters={"card_reader_type": "--None--"})
    if affected:
        frappe.db.set_value(
            "Issue",
            {"card_reader_type": "--None--"},
            "card_reader_type",
            "",
            update_modified=False,
        )
        print(f"  Cleared '--None--' on {affected} Issue(s) for field: card_reader_type")
    else:
        print("  No Issues with card_reader_type = '--None--' found — skipping")

    if frappe.db.exists("DocType", "Project Card Reader Type"):
        frappe.delete_doc(
            "DocType", "Project Card Reader Type", force=True, ignore_permissions=True
        )
        print("  Deleted orphaned DocType 'Project Card Reader Type' (and its backing table).")
    else:
        print("  DocType 'Project Card Reader Type' not found — skipping")

    frappe.db.commit()
    print("Card Reader Type migration prep complete.")
