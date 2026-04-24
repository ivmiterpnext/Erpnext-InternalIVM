import frappe


WRAP_TYPE_MIGRATIONS = {
    "IVM": "IVM Wrap",
    "Client": "Client Created",
}

STAGE_MIGRATIONS = {
    "Waiting Review": "Waiting Assignment",
    "Waiting Prioritization": "Waiting Assignment",
    "Duplicate": "Cancelled",
    "Incomplete": "Cancelled",
    "Rejected": "Cancelled",
    "Released": "Delivered",
    "Created - on Hold": "Crated - On Hold",
}


def execute():
    for old_value, new_value in STAGE_MIGRATIONS.items():
        affected = frappe.db.count("Project", filters={"stage": old_value})
        if not affected:
            continue

        frappe.db.set_value(
            "Project",
            {"stage": old_value},
            "stage",
            new_value,
            update_modified=False,
        )
        print(f"  Migrated {affected} Project(s): '{old_value}' → '{new_value}'")

    frappe.db.commit()
    print("Stage migration complete.")

    for old_value, new_value in WRAP_TYPE_MIGRATIONS.items():
        affected = frappe.db.count("Project", filters={"wrap_type": old_value})
        if not affected:
            continue
        frappe.db.set_value(
            "Project",
            {"wrap_type": old_value},
            "wrap_type",
            new_value,
            update_modified=False,
        )
        print(f"  Migrated {affected} Project(s): wrap_type '{old_value}' → '{new_value}'")

    select_fields = frappe.db.get_all(
        "Custom Field",
        filters={"dt": "Project", "fieldtype": "Select", "options": ["like", "%--None--%"]},
        fields=["fieldname"],
    )
    for cf in select_fields:
        affected = frappe.db.count("Project", filters={cf.fieldname: "--None--"})
        if not affected:
            continue
        frappe.db.set_value(
            "Project",
            {cf.fieldname: "--None--"},
            cf.fieldname,
            "",
            update_modified=False,
        )
        print(f"  Cleared '--None--' on {affected} Project(s) for field: {cf.fieldname}")

    frappe.db.commit()
    print("--None-- cleanup complete.")
