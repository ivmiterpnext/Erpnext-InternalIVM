"""
Drop orphaned legacy fields from Deployment Location left behind by the
doctype rebuild (see ivm.deployments.patches.rebuild_deployment_location),
which replaced the old tree/Opportunity-linked schema with a flat CRM
Deal/HubSpot-linked one.

created_by, modified_by1, party_name, city_name, country_name, state_name,
and location_shipping_address were Custom Fields from the old schema with
no equivalent in the new one (confirmed against SITE_FIELD_MAP in
ivm.integrations.hubspot.constants — no structured city/state/country
mapping exists). full_shipping_address/full_billing_address were derived
fields written only by Desk-UI Client Scripts with no reader anywhere.

Verified against live data before removal: all 11 Deployment Location rows
(the entire table — doctype is ~3 weeks old as of this patch) show 0/11
populated for every field above except full_shipping_address/
full_billing_address (6/11, traced to incidental manual Desk edits, not a
real dependency). No backfill required.

This patch deletes the 6 Client Scripts that wrote to these fields and the
9 Custom Field records, then drops the columns. Fixture sync never deletes
records absent from the JSON, so this must be explicit for every environment.

Safe to run repeatedly (idempotent).
"""

import frappe


def execute():
    scripts_to_delete = [
        "Address Filter Deployment Location",
        "Created Info Deployment Location",
        "Modified Info Deployment Location",
        "Fetch Full Shipping Address",
        "Full Billing Address",
        "Billing Adress Filter DL",
    ]
    for name in scripts_to_delete:
        if frappe.db.exists("Client Script", name):
            frappe.delete_doc("Client Script", name, ignore_permissions=True, force=True)
            print(f"  Deleted Client Script: {name}")
        else:
            print(f"  Client Script {name} does not exist — skipping")

    fields_to_drop = [
        "created_by",
        "modified_by1",
        "party_name",
        "city_name",
        "country_name",
        "state_name",
        "location_shipping_address",
        "full_shipping_address",
        "full_billing_address",
    ]

    for fieldname in fields_to_drop:
        cf_name = f"Deployment Location-{fieldname}"
        if frappe.db.exists("Custom Field", cf_name):
            frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
            print(f"  Deleted Custom Field: {cf_name}")
        else:
            print(f"  Custom Field {cf_name} does not exist — skipping")

    existing_columns = {
        row[0] for row in frappe.db.sql("SHOW COLUMNS FROM `tabDeployment Location`")
    }
    for fieldname in fields_to_drop:
        if fieldname not in existing_columns:
            print(f"  tabDeployment Location.{fieldname} does not exist — skipping")
            continue
        frappe.db.commit()
        frappe.db.sql_ddl(f"ALTER TABLE `tabDeployment Location` DROP COLUMN `{fieldname}`")
        print(f"  Dropped column tabDeployment Location.{fieldname}")

    frappe.clear_cache(doctype="Deployment Location")
