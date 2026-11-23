"""One-time backfill: populate Customer.icorp_client_ids (comma-joined, active iCorp
clients only) for every customer that already has at least one iCorp Client Link assigned.
Safe to re-run — just recomputes the same value."""

import frappe

from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	_refresh_icorp_client_ids_cache,
)


def execute():
	customers = frappe.get_all(
		"iCorp Client Link",
		filters={"customer": ["not in", ["", None]]},
		pluck="customer",
		distinct=True,
	)
	for customer in customers:
		_refresh_icorp_client_ids_cache(customer)
	frappe.db.commit()
	print(f"Backfilled icorp_client_ids for {len(customers)} customer(s).")
