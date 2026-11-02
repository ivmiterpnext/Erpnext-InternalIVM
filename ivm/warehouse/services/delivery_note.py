import frappe

from ivm.warehouse.services.stock_entry import get_stock_entry_items_from_warehouse_request

# Dedicated service account used to bypass ERPNext's explicit Item.check_permission()
# call inside get_item_details.py, which runs regardless of a parent doc's
# ignore_permissions flag. Created by ivm.warehouse.patches.create_automation_user.
AUTOMATION_USER = "automation@ivminc.com"


@frappe.whitelist()
def create_delivery_note_from_warehouse_request(warehouse_request_name):
	"""
	Automatically create and submit a Delivery Note for a Shipping Request.

	If the Shipping Request has a `source_build_request`, items are pulled from
	a Build WR's submitted Stock Entry, otherwise from the Shipping Request's own Stock Entries.

	Returns the Delivery Note name. Raises if no items were found and the
	Warehouse Request is not marked as a non-inventory shipment.
	"""
	existing_dn = frappe.db.get_value(
		"Delivery Note",
		{"custom_related_warehouse_request": warehouse_request_name, "docstatus": ["!=", 2]},
		"name",
	)

	if existing_dn:
		frappe.msgprint(
			f'Delivery Note <a href="/app/delivery-note/{existing_dn}">{existing_dn}</a> '
			"already exists for this Warehouse Request.",
			title="Delivery Note Exists",
			indicator="blue",
		)
		return existing_dn

	wr = frappe.get_doc("Warehouse Request", warehouse_request_name)

	if wr.source_build_request:
		items = get_stock_entry_items_from_warehouse_request(wr.source_build_request)
	else:
		items = get_stock_entry_items_from_warehouse_request(warehouse_request_name)

	if not items:
		if wr.non_inventory_shipment:
			# For non-inventory shipments, create a placeholder item row
			items = [
				{
					"item_code": "Non-Inventory Shipment",
					"item_name": "Non-Inventory Shipment",
					"description": wr.notes or "Non-inventory shipment — see Warehouse Request for details.",
					"qty": 1,
					"uom": "Nos",
					"stock_uom": "Nos",
					"conversion_factor": 1,
					"warehouse": None,
					"rate": 0,
				}
			]
		else:
			frappe.throw(
				f"No stock entry items found for Warehouse Request {warehouse_request_name}. "
				"Cannot create a Delivery Note.",
				title="Delivery Note Auto-Creation Failed",
			)

	company = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)

	customer = wr.customer
	if not customer:
		frappe.throw(
			f"Warehouse Request {warehouse_request_name} has no Customer set. "
			"Cannot create a Delivery Note without a customer.",
			title="Missing Customer",
		)

	previous_user = frappe.session.user
	frappe.set_user(AUTOMATION_USER)
	try:
		dn = frappe.new_doc("Delivery Note")
		dn.company = company
		dn.customer = customer
		dn.custom_related_warehouse_request = warehouse_request_name

		for item_data in items:
			dn.append(
				"items",
				{
					"item_code": item_data["item_code"],
					"item_name": item_data["item_name"],
					"description": item_data.get("description") or item_data["item_name"],
					"qty": item_data["qty"],
					"uom": item_data["uom"],
					"stock_uom": item_data.get("stock_uom") or item_data["uom"],
					"conversion_factor": item_data.get("conversion_factor", 1),
					"warehouse": item_data.get("warehouse"),
					"rate": item_data.get("rate", 0),
				},
			)

		dn.insert(ignore_permissions=True)
		dn.submit()

		frappe.msgprint(
			f'Delivery Note <a href="/app/delivery-note/{dn.name}">{dn.name}</a> '
			"has been created and submitted automatically.",
			title="Delivery Note Created",
			indicator="green",
		)

		if wr.source_build_request:
			build_wr = frappe.get_doc("Warehouse Request", wr.source_build_request)
			build_wr.status = "Closed"
			build_wr.save(ignore_permissions=True)

		return dn.name
	finally:
		frappe.set_user(previous_user)
