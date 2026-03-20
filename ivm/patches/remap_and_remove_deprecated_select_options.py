from __future__ import annotations
import frappe

BATCH_SIZE = 1000

def execute():
    remaps = {
        # "DocType": {
        #     "select_field": {
        #         "Old Option": "New Option",
        #     },
        # },

        "Project": {
            "stage": {
                "Waiting Review": "idk",
                "Waiting Prioritization": "idk",
                "Duplicate": "idk",
                "Created - On Hold": "Crated - On Hold",
                "Incomplete": "idk",
                "Rejected": "idk",
                "Released": "idk",
            },
        },
    }

    # Remap values
    for doctype, fields in remaps.items():
        for fieldname, mapping in fields.items():
            # Verify all new_values exist in options for select field
            meta = frappe.get_meta(doctype)
            field = next((f for f in meta.fields if f.fieldname == fieldname), None)

            if not field or not field.options:
                frappe.throw(f"Field '{fieldname}' not found or has no options in {doctype}.")
  
            options = [opt.strip() for opt in field.options.split("\n") if opt.strip()]
            for new_value in set(mapping.values()):
                if new_value not in options:
                    frappe.throw(f"Target value '{new_value}' is not a valid option for {doctype}.{fieldname}. Valid options: {options}")

            # Remap in batches for each old_value
            total_updated = 0
            for old_value, new_value in mapping.items():
                while True:
                    names = frappe.get_all(
                        doctype,
                        filters={fieldname: old_value},
                        pluck="name",
                        limit=BATCH_SIZE,
                    )

                    if not names:
                        break

                    frappe.logger().info(f"Remapping {len(names)} records from '{old_value}' to '{new_value}' in {doctype}.{fieldname}")
                    for name in names:
                        frappe.db.set_value(doctype, name, fieldname, new_value, update_modified=False)

                    frappe.db.commit()
                    total_updated += len(names)

                frappe.logger().info(f"Remapping complete: {total_updated} records updated from '{old_value}' to '{new_value}' in {doctype}.{fieldname}")

                # Verify no records remain with old_value
                remaining = frappe.db.count(doctype, {fieldname: old_value})
                if remaining > 0:
                    frappe.log_error(
                        title=f"Remapping Incomplete: {doctype}.{fieldname}",
                        message=f"{remaining} records still have value '{old_value}' after remapping."
                    )

                    frappe.throw(f"Remapping incomplete: {remaining} records still have value '{old_value}' in {doctype}.{fieldname}")

                else:
                    frappe.logger().info(f"All records successfully remapped. No '{old_value}' values remain in {doctype}.{fieldname}.")

    # Remove deprecated options after remapping
    for doctype, fields in remaps.items():
        for fieldname, mapping in fields.items():
            to_remove = list(mapping.keys())
            # Try to update Custom Field (for customizations)
            custom_field = frappe.get_all(
                "Custom Field",
                filters={"dt": doctype, "fieldname": fieldname},
                fields=["name", "options"],
                limit=1,
            )

            if custom_field:
                cf = custom_field[0]
                options = [opt.strip() for opt in (cf.options or "").split("\n") if opt.strip()]
                new_options = [opt for opt in options if opt not in to_remove]

                if len(new_options) != len(options):
                    frappe.db.set_value("Custom Field", cf.name, "options", "\n".join(new_options))
                    frappe.logger().info(f"Removed {to_remove} from {doctype}.{fieldname} (Custom Field)")

                else:
                    frappe.logger().info(f"No deprecated options found in {doctype}.{fieldname} (Custom Field)")

            else:
                # Try to update standard DocType field (not recommended, but possible)
                meta = frappe.get_meta(doctype)
                field = next((f for f in meta.fields if f.fieldname == fieldname), None)

                if field and field.options:
                    options = [opt.strip() for opt in field.options.split("\n") if opt.strip()]
                    new_options = [opt for opt in options if opt not in to_remove]

                    if len(new_options) != len(options):
                        field.options = "\n".join(new_options)
                        frappe.db.sql(
                            f"""
                            UPDATE `tabDocField`
                            SET options=%s
                            WHERE parent=%s AND fieldname=%s
                            """,
                            (field.options, doctype, fieldname),
                        )

                        frappe.logger().info(f"Removed {to_remove} from {doctype}.{fieldname} (DocField)")

                    else:
                        frappe.logger().info(f"No deprecated options found in {doctype}.{fieldname} (DocField)")

                else:
                    frappe.logger().info(f"Field {fieldname} not found in {doctype}, skipping.")

    frappe.db.commit()
