"""Review-queue layer between report_customer_disposition's output CSV and the existing merges/deletes
decision files. Queues confirmed rows from the disposition report into customer_merges.csv and
customers_to_disable.csv for execution via apply.py. Nothing here executes a merge or disable — it only
appends confirmed rows to the decision CSVs that apply.py already knows how to execute.
"""

import csv
import os
import re

import frappe

from ivm.customer_consolidation import decisions, merge_analysis


def _read_disposition_csv(path: str) -> list[dict]:
	"""Read the report CSV written by orphan_customers.report_customer_disposition."""
	with open(path, encoding="utf-8-sig", newline="") as f:
		reader = csv.DictReader(f)
		return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _extract_date_from_filename(filename: str) -> str:
	"""Extract YYYY-MM-DD from customer_disposition_report_YYYY-MM-DD.csv.

	Returns the date string, or frappe.utils.nowdate() if parsing fails."""
	match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
	if match:
		return match.group(1)
	return frappe.utils.nowdate()


@frappe.whitelist()
def queue_disables_from_report(path: str, decided_by: str | None = None) -> dict:
	"""Queue disable decisions from the disposition report into customers_to_disable.csv.

	Args:
		path: path to the disposition report CSV
		decided_by: who decided (defaults to "rule:<date>" parsed from filename)

	Returns {"queued": count, "skipped_already_queued": count}.
	"""
	frappe.only_for("System Manager")

	if decided_by is None:
		filename = os.path.basename(path)
		report_date = _extract_date_from_filename(filename)
		decided_by = f"rule:{report_date}"

	rows = _read_disposition_csv(path)

	# Filter for proposed_action == "disable"
	new_rows = []
	for row in rows:
		if row.get("proposed_action") == "disable":
			new_rows.append(
				{
					"customer": row["name"],
					"reason": row.get("reason", ""),
					"decided_by": decided_by,
					"date_decided": frappe.utils.nowdate(),
				}
			)

	# Load current and upsert
	current_rows = decisions.load_customers_to_disable()
	combined = decisions.upsert_customers_to_disable(current_rows, new_rows)

	# Write back
	decisions._write_csv(
		decisions.CUSTOMERS_TO_DISABLE_PATH,
		["customer", "reason", "decided_by", "date_decided"],
		combined,
	)

	# Count skipped (already in current_rows)
	existing_customers = {(r.get("customer") or "").strip() for r in current_rows if r.get("customer")}
	skipped = sum(1 for r in new_rows if (r.get("customer") or "").strip() in existing_customers)
	queued = len(new_rows) - skipped

	return {"queued": queued, "skipped_already_queued": skipped}


@frappe.whitelist()
def queue_merges_from_report(path: str) -> dict:
	"""Queue merge decisions from the disposition report into customer_merges.csv.

	For each row where proposed_action starts with "merge_into:" AND confirm.strip().upper() == "Y":
	- Determine if the duplicate_group is "all-dead" (every member is disable or merge_into).
	- If all-dead and no blocking conflicts (soft conflicts OK): queue with field_resolutions set.
	- If blocking conflicts or not all-dead: add to needs_manual file instead.

	Returns {"queued": count, "skipped": count, "needs_manual": count, "needs_manual_path": path or None}.
	"""
	frappe.only_for("System Manager")

	filename = os.path.basename(path)
	report_date = _extract_date_from_filename(filename)

	rows = _read_disposition_csv(path)

	# Build group membership map
	groups_by_key: dict[str, list[dict]] = {}
	for row in rows:
		group_key = row.get("duplicate_group", "")
		if group_key:
			if group_key not in groups_by_key:
				groups_by_key[group_key] = []
			groups_by_key[group_key].append(row)

	# Determine which groups are all-dead
	all_dead_groups = set()
	for group_key, group_rows in groups_by_key.items():
		all_dead = all(
			r.get("proposed_action") in ("disable", "")
			or r.get("proposed_action", "").startswith("merge_into:")
			for r in group_rows
		)
		if all_dead:
			all_dead_groups.add(group_key)

	# Process confirmed merge rows
	queued_rows = []
	needs_manual = []

	for row in rows:
		proposed_action = row.get("proposed_action", "")
		if not proposed_action.startswith("merge_into:"):
			continue

		confirm = (row.get("confirm") or "").strip().upper()
		if confirm != "Y":
			continue

		merge_from = row["name"]
		merge_into = proposed_action.split(":", 1)[1]
		group_key = row.get("duplicate_group", "")
		is_all_dead = group_key in all_dead_groups

		# Fetch customer values and field types
		field_types = merge_analysis.get_customer_field_types()
		fieldnames = list(field_types.keys())

		try:
			from_values = merge_analysis.get_customer_values(merge_from, fieldnames)
			into_values = merge_analysis.get_customer_values(merge_into, fieldnames)
		except Exception:
			# Customer doesn't exist or fetch failed
			needs_manual.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"conflicts": "Customer fetch failed",
				}
			)
			continue

		# Diff values
		diff = merge_analysis.diff_customer_values(from_values, into_values, field_types)
		conflicts = diff.get("fields_in_conflict", [])

		# Identify blocking conflicts (not in SOFT_RESOLVE_FIELDS)
		blocking_conflicts = []
		soft_conflicts = []
		for entry in conflicts:
			fieldname = entry.split(":", 1)[0].strip()
			if fieldname in merge_analysis.SOFT_RESOLVE_FIELDS:
				soft_conflicts.append(entry)
			else:
				blocking_conflicts.append(entry)

		# Decide: queue or needs_manual
		if blocking_conflicts or (conflicts and not is_all_dead):
			# Has blocking conflicts, or has any conflict and group is not all-dead
			needs_manual.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"conflicts": "; ".join(conflicts),
				}
			)
		else:
			# No blocking conflicts (soft conflicts OK if all-dead)
			field_resolutions = {}
			merge_considerations_parts = []

			if is_all_dead and soft_conflicts:
				# Auto-resolve soft conflicts to survivor's value
				for entry in soft_conflicts:
					fieldname = entry.split(":", 1)[0].strip()
					field_resolutions[fieldname] = into_values.get(fieldname, "")

				# Build merge_considerations noting what was discarded
				discarded = []
				for entry in soft_conflicts:
					fieldname = entry.split(":", 1)[0].strip()
					from_val = from_values.get(fieldname, "")
					if from_val:
						discarded.append(f"{fieldname}='{from_val}'")
				if discarded:
					merge_considerations_parts.append(
						f"auto-resolved to survivor (disposition {report_date}); discarded from loser: {'; '.join(discarded)}"
					)

			if not merge_considerations_parts:
				merge_considerations_parts.append(
					f"normalized-name duplicate; disposition report {report_date}"
				)

			queued_rows.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"evidence": f"normalized-name duplicate; disposition report {report_date}",
					"merge_considerations": "; ".join(merge_considerations_parts),
					"field_resolutions": decisions.format_field_resolutions(field_resolutions),
					"source_client_id": "",
				}
			)

	# Append to customer_merges.csv
	current_merges = decisions.load_customer_merges()
	existing_customers = {c["name"] for c in frappe.get_all("Customer", pluck="name")}

	try:
		combined_merges, skipped = decisions.append_customer_merges(
			current_merges, queued_rows, existing_customers
		)
		decisions._write_csv(
			decisions.CUSTOMER_MERGES_PATH,
			[
				"merge_from",
				"merge_into",
				"evidence",
				"merge_considerations",
				"field_resolutions",
				"source_client_id",
			],
			combined_merges,
		)
	except ValueError as e:
		frappe.log_error(
			title="Customer consolidation: queue_merges_from_report failed",
			message=str(e),
		)
		skipped = []

	# Write needs_manual if any
	needs_manual_path = None
	if needs_manual:
		site_path = frappe.get_site_path("private", "files")
		os.makedirs(site_path, exist_ok=True)
		needs_manual_path = os.path.join(site_path, f"customer_disposition_needs_manual_{report_date}.csv")

		with open(needs_manual_path, "w", newline="", encoding="utf-8") as f:
			writer = csv.DictWriter(f, fieldnames=["merge_from", "merge_into", "conflicts"])
			writer.writeheader()
			for row in needs_manual:
				writer.writerow(row)

	return {
		"queued": len(queued_rows),
		"skipped": len(skipped),
		"needs_manual": len(needs_manual),
		"needs_manual_path": needs_manual_path,
	}


@frappe.whitelist()
def queue_review_decisions_from_report(path: str) -> dict:
	"""Queue disable decisions for rows marked "review" with confirm="disable".

	Returns {"queued": count, "skipped_already_queued": count}.
	"""
	frappe.only_for("System Manager")

	rows = _read_disposition_csv(path)

	# Filter for proposed_action == "review" and confirm == "disable"
	new_rows = []
	for row in rows:
		if row.get("proposed_action") == "review":
			confirm = (row.get("confirm") or "").strip().lower()
			if confirm == "disable":
				new_rows.append(
					{
						"customer": row["name"],
						"reason": row.get("reason", ""),
						"decided_by": "manual",
						"date_decided": frappe.utils.nowdate(),
					}
				)

	# Load current and upsert
	current_rows = decisions.load_customers_to_disable()
	combined = decisions.upsert_customers_to_disable(current_rows, new_rows)

	# Write back
	decisions._write_csv(
		decisions.CUSTOMERS_TO_DISABLE_PATH,
		["customer", "reason", "decided_by", "date_decided"],
		combined,
	)

	# Count skipped
	existing_customers = {(r.get("customer") or "").strip() for r in current_rows if r.get("customer")}
	skipped = sum(1 for r in new_rows if (r.get("customer") or "").strip() in existing_customers)
	queued = len(new_rows) - skipped

	return {"queued": queued, "skipped_already_queued": skipped}
