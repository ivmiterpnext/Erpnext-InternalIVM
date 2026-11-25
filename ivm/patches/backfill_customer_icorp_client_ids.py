"""One-time backfill: populate Customer.icorp_client_ids (comma-joined, active iCorp
clients only) for every customer that already has at least one iCorp Client Link assigned.
Safe to re-run — just recomputes the same value.

Creates the Customer.icorp_client_ids Custom Field itself (idempotent) rather than relying
on it already existing: this patch runs in post_model_sync, which executes before
sync_customizations() applies ivm/ivm/custom/customer.json in the same migrate cycle, so on
a fresh environment the column would not exist yet otherwise."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	_refresh_icorp_client_ids_cache,
)


def execute():
	if not frappe.db.has_column("Customer", "icorp_client_ids"):
		create_custom_field(
			"Customer",
			{
				"fieldname": "icorp_client_ids",
				"label": "iCorp Client IDs",
				"fieldtype": "Small Text",
				"insert_after": "customer_name",
				"in_list_view": 1,
				"description": (
					"Comma-separated active iCorp client IDs assigned to this Customer via "
					"iCorp Client Link. Maintained automatically."
				),
			},
		)

	customers = frappe.get_all(
		"iCorp Client Link",
		filters={"customer": ["is", "set"]},
		pluck="customer",
		distinct=True,
	)
	for customer in customers:
		_refresh_icorp_client_ids_cache(customer)
	frappe.db.commit()
	print(f"Backfilled icorp_client_ids for {len(customers)} customer(s).")
