"""
Fix Deployment Location's autoname bug and remove one more dead Client Script.

A stale "Deployment Location-main-autoname" Property Setter (value:
"format:{customer}-DL-{######}") silently overrides the DocType JSON's own
"format:DL-{######}" autoname — the same "stale Property Setter beats JSON"
mechanism already documented for Warehouse Request's field_order (see
ivm.warehouse.patches.delete_stale_wr_field_order_property_setter). The
{customer} placeholder references a field that was dropped along with the
old tree/Opportunity-linked schema (see rebuild_deployment_location), so
Frappe cannot resolve it and has been naming every record literally
"customer-DL-NNNNNN" (the literal word "customer", not a resolved value) —
confirmed on all 11 live rows since the doctype's July rebuild. Deleting
this Property Setter restores the DocType JSON's clean "format:DL-{######}"
for all future records. The 11 existing badly-named records are left as-is
(low value, real ripple risk to rename live document names with HubSpot
site_id linkage).

Also removes "Filter Opportunities", a Client Script that queries a field
("opportunity") which no longer exists on this doctype at all — dead in the
same way as the fields/scripts removed by
ivm.deployments.patches.drop_deployment_location_legacy_fields, just found
one investigation pass later.

Safe to run repeatedly (idempotent).
"""

import frappe


def execute():
    if frappe.db.exists("Client Script", "Filter Opportunities"):
        frappe.delete_doc("Client Script", "Filter Opportunities", ignore_permissions=True, force=True)
        print("  Deleted Client Script: Filter Opportunities")
    else:
        print("  Client Script Filter Opportunities does not exist — skipping")

    ps_name = frappe.db.get_value(
        "Property Setter",
        {"doc_type": "Deployment Location", "property": "autoname"},
        "name",
    )
    if ps_name:
        frappe.delete_doc("Property Setter", ps_name, ignore_permissions=True, force=True)
        print(f"  Deleted stale Property Setter: {ps_name}")
    else:
        print("  No autoname Property Setter found on Deployment Location — skipping")

    frappe.clear_cache(doctype="Deployment Location")
