"""
Backfill the missing Delivery Note for Warehouse Request WR-11766.

WR-11766 was closed successfully (status=Closed) but its auto-Delivery-Note
creation silently no-opped, because the Stock Entry submitted against it was
typed "Material Issue" instead of "Material Transfer" --
get_stock_entry_items_from_warehouse_request() only recognizes Material
Transfer, so zero items were resolved and create_delivery_note_from_warehouse_request()
logged an Error Log entry and returned None without raising (fixed going
forward by ivm.warehouse.services.delivery_note's frappe.throw() change, and
prevented at the source by ivm.warehouse.event_handlers.stock_entry.validate()).

Confirmed with the warehouse team: the item physically already left the
building via that Material Issue -- the stock ledger impact is correct and
already posted. This script creates a paperwork-only Delivery Note (the same
"Non-Inventory Shipment" placeholder pattern used for non-inventory shipments
elsewhere in this codebase) so no additional stock ledger entry is created --
creating one against a real item/warehouse here would double-count the
removal that the Material Issue already recorded.

Not registered in patches.txt -- this targets one specific historical record
by name and has no reason to run on any other site/environment.

USAGE
-----
Dev:
    bench --site dev.local execute "exec(open('/home/lhammond/frappe-bench/apps/ivm/ivm/warehouse/recon_scripts/backfill_wr_11766_delivery_note.py').read(), globals())"

Prod (from inside the bench container):
    bench --site ivmportal.frappe.cloud execute "exec(open('/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/backfill_wr_11766_delivery_note.py').read(), globals())"

Set DRY_RUN = True (default) to preview without writing anything.
Safe to re-run: if a Delivery Note already exists for this Warehouse Request,
the script reports it and exits without creating a duplicate.
"""

import frappe

DRY_RUN = True
WR_NAME = "WR - 11766"


def execute():
	existing_dn = frappe.db.get_value(
		"Delivery Note",
		{"custom_related_warehouse_request": WR_NAME, "docstatus": ["!=", 2]},
		"name",
	)
	if existing_dn:
		print(f"Delivery Note {existing_dn} already exists for {WR_NAME} -- nothing to do.")
		return

	wr = frappe.get_doc("Warehouse Request", WR_NAME)
	if wr.status != "Closed":
		print(f"{WR_NAME} is not Closed (status={wr.status}) -- aborting, nothing to do.")
		return

	se_name = frappe.db.get_value(
		"Stock Entry",
		{"custom_warehouse_request": WR_NAME, "docstatus": 1},
		"name",
	)
	if not se_name:
		print(f"No submitted Stock Entry found linked to {WR_NAME} -- aborting.")
		return

	se = frappe.get_doc("Stock Entry", se_name)
	if not se.items:
		print(f"Stock Entry {se.name} has no item rows -- aborting.")
		return
	se_item = se.items[0]

	company = frappe.db.get_value("Warehouse", se_item.s_warehouse, "company") or wr.company

	description = (
		f"Backfilled: shipment was recorded via Material Issue {se.name} "
		f"(item {se_item.item_code}, qty {se_item.qty}) instead of Material Transfer. "
		"No additional stock ledger impact -- stock already left via that entry."
	)

	print(f"About to create Delivery Note for {WR_NAME}:")
	print(f"  company: {company}")
	print(f"  customer: {wr.customer}")
	print(f"  description: {description}")

	if DRY_RUN:
		print(
			"\nDRY_RUN is True -- no changes made. Set DRY_RUN = False to actually create the Delivery Note."
		)
		return

	dn = frappe.new_doc("Delivery Note")
	dn.company = company
	dn.customer = wr.customer
	dn.custom_related_warehouse_request = WR_NAME
	dn.append(
		"items",
		{
			"item_code": "Non-Inventory Shipment",
			"item_name": "Non-Inventory Shipment",
			"description": description,
			"qty": 1,
			"uom": "Nos",
			"stock_uom": "Nos",
			"conversion_factor": 1,
			"warehouse": None,
			"rate": 0,
		},
	)
	dn.insert(ignore_permissions=True)
	dn.submit()
	frappe.db.commit()
	print(f"\nCreated and submitted backfill Delivery Note {dn.name} for {WR_NAME}")


execute()
