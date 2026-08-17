"""
Drop all remaining orphaned/stale Property Setters on Deployment Location.

Left over from the pre-rebuild tree/Opportunity-linked schema (see
ivm.deployments.patches.rebuild_deployment_location) and from an
autoname bug fixed separately (see
ivm.deployments.patches.fix_deployment_location_naming_and_dead_script).

Verified against the live schema before removal — split into two groups:

1. Pure dead references (20): target fields that no longer exist as columns
   at all (created_on, customer, is_group, last_modified_by,
   machines_at_location, number_of_kisoks [legacy misspelled name],
   old_parent, opportunity, parent_deployment_location,
   primary_lockers_at_location, secondary_lockers_at_location), plus one
   DocType-level links_order Property Setter referencing a Link entry that
   no longer exists (the doctype's "links" array is currently empty).

2. Live overrides on fields that DO still exist (4), reviewed individually
   and confirmed safe to remove:
   - number_of_vaults-label / -allow_in_quick_entry: redundant with the
     DocType JSON's own native label ("SmartVaults"); no sibling quantity
     field (machines/kiosks/lockers) has an equivalent override.
   - shipping_address-label: was rendering the literal text
     "Shipping Address old" to every user viewing this field — a live,
     user-visible bug. Removing restores the JSON's own "Shipping Address"
     label.
   - shipping_address-read_only: field is populated by a one-way HubSpot
     sync with no write-back path found. Removing makes it editable in
     Desk per explicit direction — intentionally temporary while the
     HubSpot integration is still being finalized; read_only is expected
     to be reinstated later once sync behavior is settled (tracked
     separately, not handled by this patch).

Safe to run repeatedly (idempotent).
"""

import frappe


def execute():
    names = frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Deployment Location"},
        pluck="name",
    )

    if not names:
        print("  No Deployment Location Property Setters found — nothing to do.")
        return

    for name in names:
        frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
        print(f"  Deleted Property Setter: {name}")

    frappe.clear_cache(doctype="Deployment Location")
