"""Phase-0 dry-run analysis for the Customer / iCorp-client consolidation effort.

Classifies legacy Project.client_id values, matches iCorp clients to Frappe Customers using
multiple evidence sources, and folds in reviewed merge/assignment decisions from
ivm.customer_consolidation.decisions before producing the final picture. Read-only: no
database writes, no iCorp POST/PUT/DELETE — only GETs, frappe.get_all/get_value reads, and
local report files under private/files.
"""

import csv
import json
import os
import re
from typing import Any

import frappe
from frappe.utils import get_site_path

from ivm.integrations.icorp.api import icorp_api_get
from ivm.integrations.icorp.client_sync import fetch_icorp_clients

_CUSTOMER_NAME_SUFFIXES = frozenset(
	{
		"inc",
		"llc",
		"ltd",
		"corp",
		"corporation",
		"co",
		"company",
		"lp",
		"plc",
		"gmbh",
		"sa",
	}
)

_STATUS_SORT_ORDER = (
	"conflict",
	"project_only",
	"existing_field_only",
	"name_exact_only",
	"name_fuzzy_only",
	"confirmed",
	"assigned_manually",
	"unmatched",
)


def normalize_customer_name(name: str | None) -> str:
	"""Lowercase, strip all non-alphanumeric/whitespace characters, collapse whitespace, then strip
	trailing tokens that are in _CUSTOMER_NAME_SUFFIXES (repeat while the last remaining token is a
	suffix). Return the normalized string, or "" if name is falsy."""
	if not name:
		return ""

	normalized = re.sub(r"[^a-z0-9\s]", "", name.lower())
	normalized = re.sub(r"\s+", " ", normalized).strip()

	if not normalized:
		return ""

	while normalized:
		tokens = normalized.split()
		if tokens and tokens[-1] in _CUSTOMER_NAME_SUFFIXES:
			normalized = " ".join(tokens[:-1])
		else:
			break

	return normalized


def build_customer_name_indexes(customers: list[dict]) -> dict:
	"""Build exact and fuzzy name indexes for customers.

	customers: list of {"name": <customer docname>, "customer_name": <display name>}.
	Returns {"exact": dict[str, list[str]], "fuzzy": dict[str, list[str]]}:
	  - "exact" keys are customer_name.strip().lower(), values are lists of customer docnames
	  - "fuzzy" keys are normalize_customer_name(customer_name), values are lists of customer docnames
	Skip customers with empty/falsy customer_name entirely.
	"""
	exact: dict[str, list[str]] = {}
	fuzzy: dict[str, list[str]] = {}

	for customer in customers:
		customer_name = customer.get("customer_name")
		if not customer_name:
			continue

		docname = customer["name"]

		exact_key = customer_name.strip().lower()
		exact.setdefault(exact_key, []).append(docname)

		fuzzy_key = normalize_customer_name(customer_name)
		if fuzzy_key and fuzzy_key != exact_key:
			fuzzy.setdefault(fuzzy_key, []).append(docname)

	return {"exact": exact, "fuzzy": fuzzy}


def resolve_customer_for_name(raw_name: str | None, indexes: dict) -> dict:
	"""Resolve a customer name using exact then fuzzy indexes.

	Returns {"customer": <docname> | None, "confidence": "exact" | "fuzzy" | None, "ambiguous": bool}.
	"""
	if not raw_name:
		return {"customer": None, "confidence": None, "ambiguous": False}

	exact_key = raw_name.strip().lower()
	exact_matches = indexes["exact"].get(exact_key, [])

	if len(exact_matches) == 1:
		return {"customer": exact_matches[0], "confidence": "exact", "ambiguous": False}
	elif len(exact_matches) > 1:
		return {"customer": None, "confidence": None, "ambiguous": True}

	fuzzy_key = normalize_customer_name(raw_name)
	if fuzzy_key:
		fuzzy_matches = indexes["fuzzy"].get(fuzzy_key, [])
		if len(fuzzy_matches) == 1:
			return {"customer": fuzzy_matches[0], "confidence": "fuzzy", "ambiguous": False}
		elif len(fuzzy_matches) > 1:
			return {"customer": None, "confidence": None, "ambiguous": True}

	return {"customer": None, "confidence": None, "ambiguous": False}


def parse_legacy_client_id(raw_value: str | None) -> dict:
	"""Classify one Project.client_id raw string.

	Returns {"status": "empty" | "clean" | "malformed", "client_id": str | None, "note": str | None}.
	"""
	if not raw_value or not str(raw_value).strip():
		return {"status": "empty", "client_id": None, "note": None}

	stripped = str(raw_value).strip()

	if stripped.isdigit():
		return {"status": "clean", "client_id": stripped, "note": None}

	match = re.match(r"^(\d+)\s*\((.+)\)$", stripped)
	if match:
		client_id = match.group(1)
		paren_text = match.group(2)
		return {
			"status": "clean",
			"client_id": client_id,
			"note": f"had trailing parenthetical note: {paren_text}",
		}

	if "," in stripped:
		return {
			"status": "malformed",
			"client_id": None,
			"note": f"comma-separated multiple ids: {stripped}",
		}

	return {
		"status": "malformed",
		"client_id": None,
		"note": f"unrecognized format: {stripped}",
	}


def _build_project_customer_counts(project_rows: list[dict]) -> dict[str, dict[str, int]]:
	"""Parse each project row's client_id via parse_legacy_client_id, keep only status=='clean' rows with
	a truthy customer, and return {client_id: {customer_name: count}}."""
	result: dict[str, dict[str, int]] = {}

	for row in project_rows:
		parsed = parse_legacy_client_id(row.get("client_id"))
		if parsed["status"] == "clean" and parsed["client_id"]:
			client_id = parsed["client_id"]
			customer = row.get("customer")
			if customer:
				result.setdefault(client_id, {})
				result[client_id][customer] = result[client_id].get(customer, 0) + 1

	return result


def build_client_customer_matches(
	icorp_clients: list[dict],
	project_rows: list[dict],
	existing_customer_icorp_ids: dict[str, str],
	customers: list[dict],
	assignment_overrides: dict[str, str] | None = None,
) -> list[dict]:
	"""Pure. For every iCorp client, gather evidence from 4 sources and determine a match status.

	assignment_overrides (client_id -> customer), when given, forces status "assigned_manually" for
	that client regardless of what the evidence says — a confirmed human decision always wins.

	Returns list of row dicts with status and proposed_customer, sorted by active/status/name.
	"""
	assignment_overrides = assignment_overrides or {}
	indexes = build_customer_name_indexes(customers)
	project_customer_counts = _build_project_customer_counts(project_rows)

	rows = []

	for client in icorp_clients:
		client_id = str(client["id"])
		project_counts = project_customer_counts.get(client_id, {})
		existing_field_customer = existing_customer_icorp_ids.get(client_id)

		client_name = client.get("name") or ""
		exact_matches = indexes["exact"].get(client_name.strip().lower(), [])
		fuzzy_key = normalize_customer_name(client_name)
		fuzzy_matches = indexes["fuzzy"].get(fuzzy_key, []) if fuzzy_key else []

		distinct_customers = sorted(
			set(project_counts.keys())
			| ({existing_field_customer} if existing_field_customer else set())
			| set(exact_matches)
			| set(fuzzy_matches)
		)

		if client_id in assignment_overrides:
			status = "assigned_manually"
			proposed_customer = assignment_overrides[client_id]
		elif not distinct_customers:
			status = "unmatched"
			proposed_customer = None
		elif len(distinct_customers) == 1:
			the_customer = distinct_customers[0]
			contributing = sum(
				[
					the_customer in project_counts,
					existing_field_customer == the_customer,
					the_customer in exact_matches,
					the_customer in fuzzy_matches,
				]
			)
			if contributing >= 2:
				status = "confirmed"
			elif the_customer in project_counts:
				status = "project_only"
			elif existing_field_customer == the_customer:
				status = "existing_field_only"
			elif the_customer in exact_matches:
				status = "name_exact_only"
			else:
				status = "name_fuzzy_only"
			proposed_customer = the_customer
		else:
			status = "conflict"
			proposed_customer = None  # never guess on a conflict — a human decides

		rows.append(
			{
				"client_id": client_id,
				"client_name": client_name,
				"is_active": bool(client.get("is_active")),
				"sv_location_count_active": client.get("sv_location_count_active", 0),
				"sv_machine_count_active": client.get("sv_machine_count_active", 0),
				"parent_client_id": str(client["partner_client_id"])
				if client.get("partner_client_id")
				else "",
				"parent_client_name": client.get("partner_client_name") or "",
				"project_customers": "; ".join(
					f"{c}:{n}" for c, n in sorted(project_counts.items(), key=lambda kv: (-kv[1], kv[0]))
				),
				"existing_field_customer": existing_field_customer or "",
				"exact_name_customers": "; ".join(sorted(exact_matches)),
				"fuzzy_name_customers": "; ".join(sorted(fuzzy_matches)),
				"status": status,
				"proposed_customer": proposed_customer or "",
				"_project_customer_counts": project_counts,
				"_exact_name_customers": exact_matches,
				"_fuzzy_name_customers": fuzzy_matches,
			}
		)

	rows.sort(
		key=lambda r: (
			not r["is_active"],
			_STATUS_SORT_ORDER.index(r["status"]),
			r["client_name"].lower(),
		)
	)

	return rows


def summarize_client_matches(client_matches: list[dict]) -> dict:
	"""Pure. Count statuses. Always include all status keys (0 if none present) plus total_clients."""
	summary = {
		"total_clients": len(client_matches),
		"confirmed": 0,
		"project_only": 0,
		"existing_field_only": 0,
		"name_exact_only": 0,
		"name_fuzzy_only": 0,
		"conflict": 0,
		"assigned_manually": 0,
		"unmatched": 0,
	}

	for row in client_matches:
		status = row["status"]
		if status in summary:
			summary[status] += 1

	return summary


def build_customer_coverage(client_matches: list[dict]) -> list[dict]:
	"""Pure. Takes output of build_client_customer_matches and aggregates by customer."""
	all_customers: set[str] = set()
	for row in client_matches:
		all_customers.update(row["_project_customer_counts"].keys())
		if row["existing_field_customer"]:
			all_customers.add(row["existing_field_customer"])
		all_customers.update(row["_exact_name_customers"])
		all_customers.update(row["_fuzzy_name_customers"])
		if row["proposed_customer"]:
			all_customers.add(row["proposed_customer"])

	coverage_rows = []

	for customer in sorted(all_customers):
		confirmed_client_ids = []
		single_source_client_ids = []
		conflicting_client_ids = []
		total_project_count = 0

		for row in client_matches:
			if row["status"] in ("confirmed", "assigned_manually") and row["proposed_customer"] == customer:
				confirmed_client_ids.append(row["client_id"])

			if row["status"] in ("project_only", "existing_field_only", "name_exact_only", "name_fuzzy_only"):
				if row["proposed_customer"] == customer:
					single_source_client_ids.append(row["client_id"])

			if row["status"] == "conflict":
				if (
					customer in row["_project_customer_counts"]
					or customer == row["existing_field_customer"]
					or customer in row["_exact_name_customers"]
					or customer in row["_fuzzy_name_customers"]
				):
					conflicting_client_ids.append(row["client_id"])

			total_project_count += row["_project_customer_counts"].get(customer, 0)

		coverage_rows.append(
			{
				"customer": customer,
				"confirmed_client_ids": "; ".join(confirmed_client_ids),
				"single_source_client_ids": "; ".join(single_source_client_ids),
				"conflicting_client_ids": "; ".join(conflicting_client_ids),
				"total_project_count": total_project_count,
			}
		)

	return coverage_rows


def build_dry_run_report(
	icorp_clients: list[dict],
	project_rows: list[dict],
	existing_customer_icorp_ids: dict[str, str],
	assignment_overrides: dict[str, str] | None = None,
) -> dict:
	"""Pure classification logic. No frappe/icorp calls.

	icorp_clients: list of dicts from iCorp Client API (id, name, is_active, partner_client_id, is_partner_client).
	project_rows: list of dicts with keys "name", "customer", "client_id".
	existing_customer_icorp_ids: dict of {icorp_client_id_str: customer_name}.
	assignment_overrides: optional dict of {client_id: customer} reviewed human decisions. When a clean
	  client_id is present here AND exists in iCorp, it's classified "assignable" to the override customer
	  regardless of what project/existing-field evidence says.
	"""
	assignment_overrides = assignment_overrides or {}
	icorp_ids_set = {str(c["id"]) for c in icorp_clients}
	icorp_by_id = {str(c["id"]): c for c in icorp_clients}

	id_to_customers: dict[str, set[str]] = {}
	for row in project_rows:
		parsed = parse_legacy_client_id(row.get("client_id"))
		if parsed["status"] == "clean" and parsed["client_id"]:
			cid = parsed["client_id"]
			if row.get("customer"):
				id_to_customers.setdefault(cid, set())
				id_to_customers[cid].add(row["customer"])

	for icorp_id, customer_name in existing_customer_icorp_ids.items():
		id_to_customers.setdefault(icorp_id, set())
		id_to_customers[icorp_id].add(customer_name)

	for client_id in assignment_overrides:
		id_to_customers.setdefault(client_id, set())

	id_classifications: dict[str, dict] = {}
	for client_id in id_to_customers:
		customers = sorted(id_to_customers[client_id])
		from_override = False
		if client_id in assignment_overrides and client_id in icorp_ids_set:
			status = "assignable"
			assign_to = assignment_overrides[client_id]
			from_override = True
		elif client_id not in icorp_ids_set:
			status = "unknown_in_icorp"
			assign_to = None
		elif len(customers) == 0:
			status = "no_customer_on_any_project"
			assign_to = None
		elif len(customers) == 1:
			status = "assignable"
			assign_to = customers[0]
		else:
			status = "ambiguous"
			assign_to = None

		id_classifications[client_id] = {
			"client_id": client_id,
			"icorp_name": icorp_by_id.get(client_id, {}).get("name") if client_id in icorp_ids_set else None,
			"status": status,
			"assign_to": assign_to,
			"customers": customers,
			"from_override": from_override,
		}

	per_project = []
	projects_kept = 0
	projects_cleared_by_reason: dict[str, int] = {}
	projects_unchanged = 0

	for row in project_rows:
		parsed = parse_legacy_client_id(row.get("client_id"))
		name = row.get("name")
		customer = row.get("customer")
		legacy_client_id = row.get("client_id")

		if parsed["status"] == "empty":
			decision = "unchanged"
			reason = None
			assign_customer = None
			projects_unchanged += 1
		elif parsed["status"] == "malformed":
			decision = "clear"
			reason = parsed["note"]
			assign_customer = None
			projects_cleared_by_reason["malformed"] = projects_cleared_by_reason.get("malformed", 0) + 1
		else:
			client_id = parsed["client_id"]
			classification = id_classifications.get(client_id)
			if not classification:
				decision = "clear"
				reason = f"iCorp client {client_id} not found in iCorp"
				assign_customer = None
				projects_cleared_by_reason["unknown_in_icorp"] = (
					projects_cleared_by_reason.get("unknown_in_icorp", 0) + 1
				)
			elif classification["status"] == "unknown_in_icorp":
				decision = "clear"
				reason = f"iCorp client {client_id} not found in iCorp"
				assign_customer = None
				projects_cleared_by_reason["unknown_in_icorp"] = (
					projects_cleared_by_reason.get("unknown_in_icorp", 0) + 1
				)
			elif classification["status"] == "ambiguous":
				decision = "clear"
				reason = (
					f"iCorp client {client_id} maps to multiple customers: "
					f"{', '.join(classification['customers'])}"
				)
				assign_customer = None
				projects_cleared_by_reason["ambiguous"] = projects_cleared_by_reason.get("ambiguous", 0) + 1
			elif classification["status"] == "no_customer_on_any_project":
				decision = "clear"
				reason = "no customer determinable for this iCorp client id"
				assign_customer = None
				projects_cleared_by_reason["no_customer_on_any_project"] = (
					projects_cleared_by_reason.get("no_customer_on_any_project", 0) + 1
				)
			elif classification["status"] == "assignable":
				assign_to = classification["assign_to"]
				if customer and customer != assign_to and not classification.get("from_override"):
					decision = "clear"
					reason = (
						f"iCorp client {client_id} resolves to customer '{assign_to}' which differs "
						f"from this project's customer '{customer}'"
					)
					assign_customer = None
					projects_cleared_by_reason["customer_mismatch"] = (
						projects_cleared_by_reason.get("customer_mismatch", 0) + 1
					)
				else:
					decision = "keep"
					reason = None
					assign_customer = assign_to
					projects_kept += 1
			else:
				decision = "clear"
				reason = f"unknown classification status: {classification['status']}"
				assign_customer = None
				projects_cleared_by_reason["unknown_in_icorp"] = (
					projects_cleared_by_reason.get("unknown_in_icorp", 0) + 1
				)

		per_project.append(
			{
				"name": name,
				"customer": customer,
				"legacy_client_id": legacy_client_id,
				"parse_status": parsed["status"],
				"decision": decision,
				"reason": reason,
				"assign_customer": assign_customer,
			}
		)

	per_id_classification = list(id_classifications.values())

	icorp_active_count = sum(1 for c in icorp_clients if c.get("is_active"))
	icorp_with_parent = sum(1 for c in icorp_clients if c.get("partner_client_id") not in (0, None))
	icorp_partner_flagged = sum(1 for c in icorp_clients if c.get("is_partner_client"))

	distinct_clean_ids = len(id_classifications)
	ids_assignable = sum(1 for c in id_classifications.values() if c["status"] == "assignable")
	ids_ambiguous = sum(1 for c in id_classifications.values() if c["status"] == "ambiguous")
	ids_unknown = sum(1 for c in id_classifications.values() if c["status"] == "unknown_in_icorp")
	ids_no_customer = sum(
		1 for c in id_classifications.values() if c["status"] == "no_customer_on_any_project"
	)

	summary = {
		"total_projects_with_client_id": len(project_rows),
		"projects_kept": projects_kept,
		"projects_cleared_by_reason": projects_cleared_by_reason,
		"projects_unchanged": projects_unchanged,
		"distinct_clean_ids": distinct_clean_ids,
		"ids_assignable": ids_assignable,
		"ids_ambiguous": ids_ambiguous,
		"ids_unknown_in_icorp": ids_unknown,
		"ids_no_customer": ids_no_customer,
		"existing_customer_icorp_id_count": len(existing_customer_icorp_ids),
		"icorp_total_clients": len(icorp_clients),
		"icorp_active_clients": icorp_active_count,
		"icorp_clients_with_parent": icorp_with_parent,
		"icorp_clients_flagged_partner": icorp_partner_flagged,
	}

	return {
		"per_project": per_project,
		"per_id_classification": per_id_classification,
		"summary": summary,
	}


def gather_project_rows() -> list[dict]:
	"""frappe.get_all('Project', filters={'client_id': ['!=', '']}, fields=['name', 'customer', 'client_id'])"""
	return frappe.get_all(
		"Project",
		filters={"client_id": ["!=", ""]},
		fields=["name", "customer", "client_id"],
	)


def gather_existing_customer_icorp_ids() -> dict[str, str]:
	"""frappe.get_all('Customer', filters={'icorp_client_id': ['!=', '']}, fields=['name', 'icorp_client_id']),
	return {row.icorp_client_id: row.name for row in results}"""
	rows = frappe.get_all(
		"Customer",
		filters={"icorp_client_id": ["!=", ""]},
		fields=["name", "icorp_client_id"],
	)
	return {row["icorp_client_id"]: row["name"] for row in rows}


def gather_customers() -> list[dict]:
	"""frappe.get_all('Customer', fields=['name', 'customer_name'])"""
	return frappe.get_all("Customer", fields=["name", "customer_name"])


def gather_hubspot_candidates() -> dict:
	"""Two parts: deals with both org+customer, and name-matches.

	Returns {"deals_with_both": [...], "name_matches": [...]}.
	"""
	deals_with_both = []
	deals = frappe.get_all(
		"CRM Deal",
		filters={"organization": ["!=", ""], "custom_customer": ["!=", ""]},
		fields=["name", "organization", "custom_customer"],
	)
	for deal in deals:
		org_doc = frappe.db.get_value(
			"CRM Organization",
			deal["organization"],
			["custom_hubspot_company_id", "organization_name"],
			as_dict=True,
		)
		if org_doc:
			deals_with_both.append(
				{
					"deal": deal["name"],
					"organization": deal["organization"],
					"organization_name": org_doc.get("organization_name"),
					"hubspot_company_id": org_doc.get("custom_hubspot_company_id"),
					"customer": deal["custom_customer"],
				}
			)

	name_matches = []
	deal_customers = {d["customer"] for d in deals_with_both}

	orgs = frappe.get_all(
		"CRM Organization",
		filters={"custom_hubspot_company_id": ["!=", ""]},
		fields=["name", "organization_name", "custom_hubspot_company_id"],
	)

	customers = frappe.get_all("Customer", fields=["name", "customer_name"])
	customer_name_map = {c["customer_name"]: c["name"] for c in customers if c.get("customer_name")}

	for org in orgs:
		org_name = org.get("organization_name")
		if org_name and org_name in customer_name_map:
			matched_customer = customer_name_map[org_name]
			if matched_customer not in deal_customers:
				name_matches.append(
					{
						"organization": org["name"],
						"organization_name": org_name,
						"hubspot_company_id": org.get("custom_hubspot_company_id"),
						"matched_customer_name": matched_customer,
					}
				)

	return {
		"deals_with_both": deals_with_both,
		"name_matches": name_matches,
	}


def _write_list_column_csv(path: str, header: list[str], rows: list[dict]) -> None:
	"""Write rows to a CSV where any list-valued cell is joined with ' | '."""
	with open(path, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(header)
		for row in rows:
			out = []
			for col in header:
				value = row.get(col, "")
				if isinstance(value, list):
					out.append(" | ".join(str(v) for v in value))
				else:
					out.append(value)
			writer.writerow(out)


def write_report_files(
	dry_run_report: dict,
	hubspot_report: dict,
	client_matches: list[dict],
	customer_coverage: list[dict],
	client_match_summary: dict,
	merge_check_rows: list[dict] | None = None,
	validated_assignments: list[dict] | None = None,
	client_match_summary_before_decisions: dict | None = None,
	decisions_summary: dict | None = None,
) -> dict:
	"""Write CSV and JSON files under private/files. Return dict of {filename: path}."""
	merge_check_rows = merge_check_rows or []
	validated_assignments = validated_assignments or []
	client_match_summary_before_decisions = client_match_summary_before_decisions or {}
	decisions_summary = decisions_summary or {}

	private_files_dir = get_site_path("private", "files")
	os.makedirs(private_files_dir, exist_ok=True)

	icorp_review_path = os.path.join(private_files_dir, "icorp_client_review.csv")
	with open(icorp_review_path, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["project", "customer", "legacy_client_id", "reason"])
		for row in dry_run_report["per_project"]:
			if row["decision"] == "clear":
				writer.writerow(
					[
						row["name"],
						row["customer"] or "",
						row["legacy_client_id"] or "",
						row["reason"] or "",
					]
				)

	hubspot_review_path = os.path.join(private_files_dir, "hubspot_customer_review.csv")
	with open(hubspot_review_path, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["match_type", "organization", "organization_name", "hubspot_company_id", "customer"])
		for row in hubspot_report["deals_with_both"]:
			writer.writerow(
				[
					"deal_link",
					row["organization"],
					row["organization_name"] or "",
					row["hubspot_company_id"] or "",
					row["customer"],
				]
			)
		for row in hubspot_report["name_matches"]:
			writer.writerow(
				[
					"name_match",
					row["organization"],
					row["organization_name"] or "",
					row["hubspot_company_id"] or "",
					row["matched_customer_name"],
				]
			)

	matches_path = os.path.join(private_files_dir, "icorp_client_customer_matches.csv")
	with open(matches_path, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(
			[
				"client_id",
				"client_name",
				"is_active",
				"sv_location_count_active",
				"sv_machine_count_active",
				"parent_client_id",
				"parent_client_name",
				"project_customers",
				"existing_field_customer",
				"exact_name_customers",
				"fuzzy_name_customers",
				"status",
				"proposed_customer",
			]
		)
		for row in client_matches:
			writer.writerow(
				[
					row["client_id"],
					row["client_name"],
					row["is_active"],
					row["sv_location_count_active"],
					row["sv_machine_count_active"],
					row["parent_client_id"],
					row["parent_client_name"],
					row["project_customers"],
					row["existing_field_customer"],
					row["exact_name_customers"],
					row["fuzzy_name_customers"],
					row["status"],
					row["proposed_customer"],
				]
			)

	coverage_path = os.path.join(private_files_dir, "customer_client_coverage.csv")
	with open(coverage_path, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(
			[
				"customer",
				"confirmed_client_ids",
				"single_source_client_ids",
				"conflicting_client_ids",
				"total_project_count",
			]
		)
		for row in customer_coverage:
			writer.writerow(
				[
					row["customer"],
					row["confirmed_client_ids"],
					row["single_source_client_ids"],
					row["conflicting_client_ids"],
					row["total_project_count"],
				]
			)

	merges_check_path = os.path.join(private_files_dir, "planned_merges_check.csv")
	merges_rows_for_csv = []
	for row in merge_check_rows:
		merges_rows_for_csv.append(
			{
				**row,
				"validation_errors": row.get("validation_errors") or [],
			}
		)
	_write_list_column_csv(
		merges_check_path,
		[
			"merge_from",
			"merge_into",
			"resolved_into",
			"status",
			"valid",
			"ready_to_merge",
			"validation_errors",
			"linked_records_from",
			"linked_records_into",
			"fields_to_copy",
			"fields_in_conflict",
			"unresolved_field_conflicts",
			"contacts_from",
			"contacts_into",
			"possible_duplicate_contacts",
			"addresses_from",
			"addresses_into",
			"possible_duplicate_addresses",
			"icorp_clients_from",
			"icorp_clients_into",
			"evidence",
			"merge_considerations",
		],
		merges_rows_for_csv,
	)

	assignments_check_path = os.path.join(private_files_dir, "client_assignments_check.csv")
	assignments_rows_for_csv = []
	for row in validated_assignments:
		errors = row.get("errors") or []
		assignments_rows_for_csv.append(
			{
				"client_id": row.get("client_id", ""),
				"customer": row.get("customer", ""),
				"resolved_customer": row.get("resolved_customer", ""),
				"valid": "no" if errors else "yes",
				"errors": errors,
				"evidence": row.get("evidence", ""),
			}
		)
	_write_list_column_csv(
		assignments_check_path,
		["client_id", "customer", "resolved_customer", "valid", "errors", "evidence"],
		assignments_rows_for_csv,
	)

	summary_path = os.path.join(private_files_dir, "icorp_migration_summary.json")
	summary_data = dry_run_report["summary"].copy()
	summary_data["hubspot_deals_with_both"] = len(hubspot_report["deals_with_both"])
	summary_data["hubspot_name_matches"] = len(hubspot_report["name_matches"])
	summary_data["client_match_summary"] = client_match_summary
	summary_data["client_match_summary_before_decisions"] = client_match_summary_before_decisions
	summary_data["decisions_summary"] = decisions_summary
	with open(summary_path, "w") as f:
		json.dump(summary_data, f, indent=2)

	return {
		"icorp_client_review": icorp_review_path,
		"hubspot_customer_review": hubspot_review_path,
		"icorp_client_customer_matches": matches_path,
		"customer_client_coverage": coverage_path,
		"planned_merges_check": merges_check_path,
		"client_assignments_check": assignments_check_path,
		"icorp_migration_summary": summary_path,
	}


@frappe.whitelist()
def run_icorp_migration_dry_run(write_files: bool = True) -> dict:
	"""Orchestrate dry-run analysis, folding in reviewed merge/assignment decisions.

	Return summary, hubspot_summary, client matches (before and after decisions), and file paths.
	"""
	frappe.only_for("System Manager")

	if isinstance(write_files, str):
		write_files = write_files.lower() not in ("0", "false", "")

	from ivm.customer_consolidation import decisions

	icorp_clients = fetch_icorp_clients()
	project_rows = gather_project_rows()
	existing_customer_icorp_ids = gather_existing_customer_icorp_ids()
	customers = gather_customers()
	hubspot_report = gather_hubspot_candidates()

	existing_customers = {c["name"] for c in customers}
	icorp_client_ids = {str(c["id"]) for c in icorp_clients}

	client_matches_before = build_client_customer_matches(
		icorp_clients, project_rows, existing_customer_icorp_ids, customers
	)

	merges = decisions.load_customer_merges()
	validated_merges = decisions.validate_customer_merges(merges, existing_customers)
	valid_merges = [m for m in validated_merges if not m["errors"]]
	merge_map, _cycle_members = decisions.resolve_merge_map(valid_merges)

	assignments = decisions.load_client_assignments()
	validated_assignments = decisions.validate_client_assignments(
		assignments, existing_customers, icorp_client_ids, merge_map
	)
	assignment_overrides = {
		row["client_id"]: row["resolved_customer"] for row in validated_assignments if not row["errors"]
	}

	mapped_project_rows, mapped_existing_ids, mapped_customers = decisions.apply_merge_map(
		project_rows, existing_customer_icorp_ids, customers, merge_map
	)

	dry_run_report = build_dry_run_report(
		icorp_clients, mapped_project_rows, mapped_existing_ids, assignment_overrides=assignment_overrides
	)
	client_matches = build_client_customer_matches(
		icorp_clients,
		mapped_project_rows,
		mapped_existing_ids,
		mapped_customers,
		assignment_overrides=assignment_overrides,
	)
	customer_coverage = build_customer_coverage(client_matches)
	client_match_summary = summarize_client_matches(client_matches)
	client_match_summary_before_decisions = summarize_client_matches(client_matches_before)

	from ivm.customer_consolidation import merge_analysis

	merge_check_rows = merge_analysis.build_merge_check_rows(validated_merges, client_matches_before)

	decisions_summary = {
		"merges_total": len(validated_merges),
		"merges_pending": sum(1 for m in validated_merges if m["status"] == "pending"),
		"merges_already_applied": sum(1 for m in validated_merges if m["status"] == "already_applied"),
		"merges_invalid": sum(1 for m in validated_merges if m["status"] == "invalid"),
		"assignments_total": len(validated_assignments),
		"assignments_valid": sum(1 for a in validated_assignments if not a["errors"]),
		"assignments_invalid": sum(1 for a in validated_assignments if a["errors"]),
	}

	result = {
		"summary": dry_run_report["summary"],
		"hubspot_summary": {
			"deals_with_both": len(hubspot_report["deals_with_both"]),
			"name_matches": len(hubspot_report["name_matches"]),
		},
		"client_match_summary": client_match_summary,
		"client_match_summary_before_decisions": client_match_summary_before_decisions,
		"decisions_summary": decisions_summary,
		"files": {},
	}

	if write_files:
		result["files"] = write_report_files(
			dry_run_report,
			hubspot_report,
			client_matches,
			customer_coverage,
			client_match_summary,
			merge_check_rows=merge_check_rows,
			validated_assignments=validated_assignments,
			client_match_summary_before_decisions=client_match_summary_before_decisions,
			decisions_summary=decisions_summary,
		)

	return result
