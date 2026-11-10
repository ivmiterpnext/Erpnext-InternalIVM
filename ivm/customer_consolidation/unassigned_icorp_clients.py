"""Report of iCorp clients with no Customer assigned yet (iCorp Client Link.customer blank),
for human review. Optionally syncs from iCorp first so the Link table reflects iCorp's current
client list before reporting -- sync_icorp_client_links() only ever upserts identity fields
(client_name, is_active, is_partner_client, parent_client, location/machine counts), never the
customer or any review field, so it's safe to call before this read-only report.
"""

import csv
import os

import frappe

from ivm.customer_consolidation import apply


def find_unassigned_icorp_clients(sync_first: bool = True) -> list[dict]:
	"""Find all iCorp Client Link records with no Customer assigned (customer field blank).

	Args:
		sync_first: If True, call sync_icorp_client_links() first to ensure the Link table
			reflects iCorp's current client list. Defaults to True.

	Returns:
		List of dicts with fields: icorp_client_id, client_name, is_active, is_partner_client,
		parent_client, customer, assignment_source, review_status, match_status,
		proposed_customer, parent_customer, has_multiple_customer_candidates,
		duplicate_name_siblings, match_evidence. Sorted by is_active desc, client_name asc.
	"""
	if sync_first:
		apply.sync_icorp_client_links()

	fields = [
		"icorp_client_id",
		"client_name",
		"is_active",
		"is_partner_client",
		"parent_client",
		"customer",
		"assignment_source",
		"review_status",
		"match_status",
		"proposed_customer",
		"parent_customer",
		"has_multiple_customer_candidates",
		"duplicate_name_siblings",
		"match_evidence",
	]

	rows = frappe.get_all(
		"iCorp Client Link",
		filters={"customer": ["is", "not set"]},
		fields=fields,
		order_by="is_active desc, client_name asc",
	)

	return rows


def report_unassigned_icorp_clients(sync_first: bool = True) -> str:
	"""Generate and write unassigned iCorp clients report CSV. Return path.

	Args:
		sync_first: If True, call sync_icorp_client_links() first. Defaults to True.

	Returns:
		Path to the written CSV file.
	"""
	rows = find_unassigned_icorp_clients(sync_first=sync_first)

	# Write to private files
	site_path = frappe.get_site_path("private", "files")
	os.makedirs(site_path, exist_ok=True)
	path = os.path.join(site_path, f"unassigned_icorp_clients_report_{frappe.utils.nowdate()}.csv")

	header = [
		"icorp_client_id",
		"client_name",
		"is_active",
		"is_partner_client",
		"parent_client",
		"customer",
		"assignment_source",
		"review_status",
		"match_status",
		"proposed_customer",
		"parent_customer",
		"has_multiple_customer_candidates",
		"duplicate_name_siblings",
		"match_evidence",
	]

	with open(path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=header)
		writer.writeheader()
		for row in rows:
			writer.writerow(row)

	print(f"Wrote {len(rows)} unassigned iCorp client(s) to {path}")  # noqa: T201
	return path
