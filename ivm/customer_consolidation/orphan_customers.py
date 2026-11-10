"""Read-only report of Customers with zero or low connections to anything else in the system, so a
human can review what data each one holds before deciding whether to queue it for deletion via
customers_to_disable.csv. "Connections" means rows across every Link field anywhere in
the install that points at Customer (Projects, Sales Orders, Quotations, Issues, iCorp Client
Link, etc. -- via merge_analysis.get_customer_link_fields) and Dynamic Link rows (Contact, Address).
Customers already queued in customer_merges.csv (merge_from) are excluded since they're already
being handled by the merge workflow. Suggestion-only links (iCorp Client Link.proposed_customer,
iCorp Client Link Customer Candidate.customer, Customer.parent_account) do not count toward the
link total but still appear in the report's link_breakdown column.
"""

import csv
import os
import re

import frappe

from ivm.customer_consolidation import decisions, merge_analysis

_SKIP_FIELDS = frozenset(
	{
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"naming_series",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
		"customer_name",
	}
)

SUGGESTION_LINK_FIELDS = frozenset(
	{
		("iCorp Client Link", "proposed_customer"),
		("iCorp Client Link Customer Candidate", "customer"),
		("Customer", "parent_account"),
	}
)

_TV_SUFFIX_RE = re.compile(r"\(\s*tv\s*\)", re.IGNORECASE)

BENIGN_LINK_LABELS = frozenset({"Contact (dynamic link)", "Address (dynamic link)"})


def count_links_for_all_customers() -> dict[str, dict[str, int]]:
	"""Bulk-count linked records for all customers in one pass per link field.

	Returns dict keyed by customer name, with sub-dict mapping label (e.g. "Project.customer")
	to count. Customers with zero links anywhere won't appear as a key.
	Label format matches merge_analysis.count_linked_records exactly."""
	result: dict[str, dict[str, int]] = {}
	link_fields = merge_analysis.get_customer_link_fields()

	# Bulk count for each link field
	for field in link_fields:
		try:
			rows = frappe.db.sql(
				f"""SELECT `{field["fieldname"]}`, COUNT(*) as cnt
				   FROM `tab{field["parent"]}`
				   WHERE `{field["fieldname"]}` IS NOT NULL AND `{field["fieldname"]}` != ''
				   GROUP BY `{field["fieldname"]}`""",
				as_dict=True,
			)
			label = f"{field['parent']}.{field['fieldname']}"
			for row in rows:
				customer = row[field["fieldname"]]
				if customer not in result:
					result[customer] = {}
				result[customer][label] = row["cnt"]
		except Exception:
			continue

	# Bulk count for Dynamic Link
	try:
		rows = frappe.db.sql(
			"""SELECT link_name, parenttype, COUNT(*) as cnt
			   FROM `tabDynamic Link`
			   WHERE link_doctype='Customer'
			   GROUP BY link_name, parenttype""",
			as_dict=True,
		)
		for row in rows:
			customer = row["link_name"]
			if customer not in result:
				result[customer] = {}
			label = f"{row['parenttype']} (dynamic link)"
			result[customer][label] = row["cnt"]
	except Exception:
		pass

	return result


def find_orphan_customers() -> list[str]:
	"""Return sorted list of Customer names with zero linked records (excluding suggestion-only links)
	and not in merge_from."""
	customers = frappe.get_all("Customer", fields=["name"])
	merge_from_set = {r["merge_from"] for r in decisions.load_customer_merges() if r.get("merge_from")}
	counts_dict = count_links_for_all_customers()

	orphans = []
	for row in customers:
		customer = row["name"]
		if customer in merge_from_set:
			continue

		link_counts = counts_dict.get(customer, {})
		# Sum only non-suggestion links
		total_links = sum(v for label, v in link_counts.items() if not _is_suggestion_link(label))

		if total_links == 0:
			orphans.append(customer)

	return sorted(orphans)


def _is_suggestion_link(label: str) -> bool:
	"""Check if a label (e.g. 'iCorp Client Link.proposed_customer') corresponds to a suggestion field."""
	for parent, fieldname in SUGGESTION_LINK_FIELDS:
		if label == f"{parent}.{fieldname}":
			return True
	return False


def _non_default_fields(customer: str) -> str:
	"""Return formatted string of non-default field values, or empty string.
	A field is considered "default" if it's blank (None, "", 0) or matches the field's
	default value from the meta. This is for reporting purposes — to show a human what
	data a Customer holds beyond the bare minimum."""
	meta = frappe.get_meta("Customer")

	# Collect fields to check
	fields_to_check = []
	for field in meta.fields:
		if field.fieldname in _SKIP_FIELDS:
			continue
		if field.fieldtype in frappe.model.no_value_fields:
			continue
		if field.fieldtype in frappe.model.table_fields:
			continue
		fields_to_check.append(field)

	if not fields_to_check:
		return ""

	# Fetch customer values
	fieldnames = [f.fieldname for f in fields_to_check]
	row = frappe.db.get_value("Customer", customer, fieldnames, as_dict=True) or {}

	# Check each field for non-default value
	non_default = []
	for field in fields_to_check:
		value = row.get(field.fieldname)

		# Treat as blank/default if: None, "", 0
		if value in (None, "", 0):
			continue

		# Also skip if it matches the field's meta default (if one is defined)
		if field.default:
			if str(value).strip() == str(field.default).strip():
				continue

		non_default.append(f"{field.fieldname}: {value}")

	return "; ".join(non_default)


def _child_table_summary(customer: str) -> str:
	"""Return formatted string of non-zero child table row counts, or empty string."""
	meta = frappe.get_meta("Customer")

	# Map fieldnames to child doctypes
	child_tables = {}
	for field in meta.fields:
		if field.fieldtype in ("Table", "Table MultiSelect"):
			child_tables[field.fieldname] = field.options

	counts = []
	for fieldname, child_doctype in child_tables.items():
		n = frappe.db.count(child_doctype, {"parent": customer, "parenttype": "Customer"})
		if n:
			counts.append(f"{fieldname}:{n}")

	return "; ".join(counts)


def report_low_link_customers(max_links: int = 10) -> str:
	"""Generate and write low-link customers report CSV incrementally. Return path.

	Customers with total_links <= max_links (excluding suggestion-only links) are included.
	Writes each row to disk immediately as it's discovered, flushing after every row,
	so an interrupted run leaves a valid, readable partial CSV."""
	# Build output path
	site_path = frappe.get_site_path("private", "files")
	os.makedirs(site_path, exist_ok=True)
	path = os.path.join(site_path, f"low_link_customers_report_{frappe.utils.nowdate()}.csv")

	# Bulk-count all customers once
	counts_dict = count_links_for_all_customers()
	customers = frappe.get_all("Customer", fields=["name"])
	merge_from_set = {r["merge_from"] for r in decisions.load_customer_merges() if r.get("merge_from")}

	# Filter and sort
	filtered = []
	for row in customers:
		customer = row["name"]
		if customer in merge_from_set:
			continue

		link_counts = counts_dict.get(customer, {})
		total_links = sum(v for label, v in link_counts.items() if not _is_suggestion_link(label))

		if total_links <= max_links:
			filtered.append((total_links, customer, link_counts))

	filtered.sort(key=lambda x: (x[0], x[1]))  # Sort by total_links, then name

	# Open file once, write header immediately
	header = [
		"name",
		"customer_name",
		"creation",
		"disabled",
		"total_links",
		"link_breakdown",
		"non_default_fields",
		"child_table_rows",
	]
	count = 0

	with open(path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=header)
		writer.writeheader()
		f.flush()
		os.fsync(f.fileno())

		# Stream each customer as it's processed
		for total_links, customer, link_counts in filtered:
			customer_name = frappe.db.get_value("Customer", customer, "customer_name") or ""
			creation = frappe.db.get_value("Customer", customer, "creation") or ""
			creation_date = str(creation).split(" ")[0] if creation else ""
			disabled = frappe.db.get_value("Customer", customer, "disabled") or 0

			# Build link_breakdown: sorted labels with counts, marking suggestions
			breakdown_parts = []
			for label in sorted(link_counts.keys()):
				cnt = link_counts[label]
				if _is_suggestion_link(label):
					breakdown_parts.append(f"{label}:{cnt} (suggestion)")
				else:
					breakdown_parts.append(f"{label}:{cnt}")
			link_breakdown = "; ".join(breakdown_parts)

			row = {
				"name": customer,
				"customer_name": customer_name,
				"creation": creation_date,
				"disabled": disabled,
				"total_links": total_links,
				"link_breakdown": link_breakdown,
				"non_default_fields": _non_default_fields(customer),
				"child_table_rows": _child_table_summary(customer),
			}

			writer.writerow(row)
			f.flush()
			os.fsync(f.fileno())
			count += 1

	print(f"Wrote {count} customer(s) with <= {max_links} link(s) to {path}")  # noqa: T201
	return path


def report_orphan_customers() -> str:
	"""Generate and write orphan customers report CSV. Return path.

	Wrapper around report_low_link_customers(max_links=0) for backward compatibility."""
	return report_low_link_customers(max_links=0)


def operational_link_total(link_counts: dict[str, int]) -> int:
	"""Sum counts for labels that are neither suggestion links nor benign (Contact/Address dynamic links).

	Returns the total count of operational links (everything except suggestions and Contact/Address)."""
	total = 0
	for label, count in link_counts.items():
		if not _is_suggestion_link(label) and label not in BENIGN_LINK_LABELS:
			total += count
	return total


def fetch_opportunity_summary() -> dict[str, dict]:
	"""Fetch Opportunity data grouped by customer.

	Returns {customer: {"stages": {stage: count}, "last_txn": "YYYY-MM-DD" or None, "has_won": bool}}.
	Stages with NULL/empty sales_stage are keyed as "".
	last_txn is the maximum transaction_date across all stage-groups for that customer.
	has_won is True if any stage-group has sales_stage == "Closed Won".
	"""
	rows = frappe.db.sql(
		"""SELECT party_name, sales_stage, MAX(transaction_date) as last_txn
		   FROM tabOpportunity
		   WHERE opportunity_from='Customer' AND party_name IS NOT NULL AND party_name != ''
		   GROUP BY party_name, sales_stage""",
		as_dict=True,
	)

	result: dict[str, dict] = {}
	for row in rows:
		customer = row["party_name"]
		stage = row["sales_stage"] or ""
		last_txn = row["last_txn"]

		if customer not in result:
			result[customer] = {"stages": {}, "last_txn": None, "has_won": False}

		result[customer]["stages"][stage] = result[customer]["stages"].get(stage, 0) + 1

		if last_txn:
			last_txn_str = str(last_txn).split(" ")[0]
			if result[customer]["last_txn"] is None or last_txn_str > result[customer]["last_txn"]:
				result[customer]["last_txn"] = last_txn_str

		if stage == "Closed Won":
			result[customer]["has_won"] = True

	return result


def fetch_communication_counts() -> dict[str, int]:
	"""Fetch Communication counts grouped by reference_name (customer).

	Returns {customer: count}."""
	rows = frappe.db.sql(
		"""SELECT reference_name, COUNT(*) as cnt
		   FROM tabCommunication
		   WHERE reference_doctype='Customer' AND reference_name IS NOT NULL AND reference_name != ''
		   GROUP BY reference_name""",
		as_dict=True,
	)
	return {row["reference_name"]: row["cnt"] for row in rows}


def classify_customer(
	link_counts: dict[str, int], opp_summary: dict | None, creation, cutoff_date
) -> tuple[str, str]:
	"""Classify a Customer as keep / review / disable based on operational links and opportunity data.

	Args:
		link_counts: dict mapping label -> count (from count_links_for_all_customers)
		opp_summary: dict with "stages", "last_txn", "has_won" keys (from fetch_opportunity_summary), or None
		creation: Customer creation date (str, datetime, or date object)
		cutoff_date: datetime.date object for recency threshold

	Returns (action, reason) tuple where action is one of "keep", "review", "disable".

	Logic:
	1. If operational_link_total(link_counts) > 0: return ("keep", "<reason citing which label(s)>")
	2. Else if opp_summary and opp_summary.get("has_won"): return ("review", "has a Closed Won opportunity")
	3. Else if creation >= cutoff_date: return ("review", "created on or after <cutoff>")
	4. Else if opp_summary and opp_summary.get("last_txn") >= cutoff_date: return ("review", "opportunity transaction_date on or after <cutoff>")
	5. Else: return ("disable", "no operational links, no recent/won opportunity")
	"""
	opp_summary = opp_summary or {}

	# Normalize creation to YYYY-MM-DD string
	creation_str = str(creation).split(" ")[0] if creation else ""
	cutoff_str = cutoff_date.isoformat()

	# Rule 1: operational links present
	op_total = operational_link_total(link_counts)
	if op_total > 0:
		# Build reason citing which labels
		labels_with_counts = []
		for label, count in sorted(link_counts.items()):
			if not _is_suggestion_link(label) and label not in BENIGN_LINK_LABELS:
				labels_with_counts.append(f"{label}:{count}")
		reason = ", ".join(labels_with_counts) if labels_with_counts else "operational links"
		return ("keep", reason)

	# Rule 2: has a Closed Won opportunity
	if opp_summary and opp_summary.get("has_won"):
		return ("review", "has a Closed Won opportunity")

	# Rule 3: created on or after cutoff
	if creation_str and creation_str >= cutoff_str:
		return ("review", f"created on or after {cutoff_str}")

	# Rule 4: opportunity transaction_date on or after cutoff
	if opp_summary and opp_summary.get("last_txn"):
		last_txn = opp_summary["last_txn"]
		if last_txn >= cutoff_str:
			return ("review", f"opportunity transaction_date on or after {cutoff_str}")

	# Rule 5: no operational links, no recent/won opportunity
	return ("disable", "no operational links, no recent/won opportunity")


def normalize_for_dedupe(name: str | None) -> str:
	"""Normalize a customer name for deduplication.

	Strips (TV) suffix (case-insensitive, allowing internal whitespace).
	Strips trailing " - <digits>" pattern.
	Then applies normalize_customer_name from dry_run.
	Returns "" if name is falsy."""
	if not name:
		return ""

	import re

	from ivm.customer_consolidation.dry_run import normalize_customer_name

	# Strip (TV) suffix
	result = re.sub(r"\(\s*tv\s*\)", "", name, flags=re.IGNORECASE)

	# Strip trailing " - <digits>"
	result = re.sub(r"\s+-\s+\d+\s*$", "", result)

	# Apply normalize_customer_name
	return normalize_customer_name(result)


def build_duplicate_groups(
	customers: list[dict],
	classifications: dict[str, tuple[str, str]],
	link_totals: dict[str, int],
	distinct_pairs: set[frozenset],
) -> dict[str, dict]:
	"""Build duplicate groups from normalized customer names.

	Args:
		customers: list of {"name": ..., "customer_name": ..., "creation": ...} dicts
		classifications: {customer_name: (action, reason)} from classify_customer
		link_totals: {customer_name: operational_link_total}
		distinct_pairs: set of frozensets from decisions.load_distinct_pairs()

	Returns {customer_name: {"group_key": normalized_name, "survivor": survivor_name, "is_survivor": bool}}
	only for customers in groups of size > 1. Customers not in any group are absent from the dict.

	Within a group, survivor is chosen by: (action rank: keep=0/review=1/disable=2, then -link_totals, then non-"(TV)" before "(TV)", then creation asc, then name asc).
	"""
	from collections import defaultdict

	# Group by normalized name
	groups_by_key: dict[str, list[str]] = defaultdict(list)
	for customer in customers:
		name = customer["name"]
		customer_name = customer.get("customer_name", "")
		normalized = normalize_for_dedupe(customer_name)
		if normalized:
			groups_by_key[normalized].append(name)

	# Build a graph to handle distinct_pairs: customers in same bucket are connected UNLESS in distinct_pairs
	def _find_connected_components(bucket: list[str]) -> list[list[str]]:
		"""Union-find to split bucket by distinct_pairs."""
		if len(bucket) <= 1:
			return [bucket]

		parent = {name: name for name in bucket}

		def find(x):
			if parent[x] != x:
				parent[x] = find(parent[x])
			return parent[x]

		def union(x, y):
			px, py = find(x), find(y)
			if px != py:
				parent[px] = py

		# Connect all pairs NOT in distinct_pairs
		for i, a in enumerate(bucket):
			for b in bucket[i + 1 :]:
				pair = frozenset({a, b})
				if pair not in distinct_pairs:
					union(a, b)

		# Group by root
		components: dict[str, list[str]] = defaultdict(list)
		for name in bucket:
			components[find(name)].append(name)

		return list(components.values())

	result = {}

	for group_key, bucket in groups_by_key.items():
		# Split by distinct_pairs
		components = _find_connected_components(bucket)

		for component in components:
			if len(component) <= 1:
				continue  # Not a duplicate group

			# Pick survivor: sort by (action rank, -link_totals, is_tv, creation, name). A "(TV)" record
			# is a known duplicate marker from the 2023 import, so on an otherwise-equal tie the
			# non-"(TV)" record survives.
			def _sort_key(name):
				action, _ = classifications.get(name, ("disable", ""))
				action_rank = {"keep": 0, "review": 1, "disable": 2}.get(action, 2)
				link_total = link_totals.get(name, 0)
				is_tv = 1 if _TV_SUFFIX_RE.search(name) else 0
				creation = next((c["creation"] for c in customers if c["name"] == name), "")
				creation_str = str(creation).split(" ")[0] if creation else ""
				return (action_rank, -link_total, is_tv, creation_str, name)

			survivor = sorted(component, key=_sort_key)[0]

			# Record all members
			for name in component:
				result[name] = {
					"group_key": group_key,
					"survivor": survivor,
					"is_survivor": (name == survivor),
				}

	return result


def report_customer_disposition(cutoff: str = "2024-01-01") -> str:
	"""Generate and write customer disposition report CSV. Return path.

	Classifies ALL Customers (not just low-link ones) as keep / review / disable / merge_into / already_disabled.
	Excludes customers that are pending merge_from in customer_merges.csv.

	Columns: name, customer_name, creation, disabled, operational_links, link_breakdown, opportunity_breakdown,
	last_opportunity_date, communication_count, duplicate_group, proposed_survivor, proposed_action, reason, confirm

	Sorted by (proposed_action rank: disable=0, merge_into=1, review=2, keep=3, already_disabled=4, then alphabetically within group/action, then name).

	For already_disabled rows (customer disabled=1, regardless of what the live rule would otherwise classify it as), confirm is pre-filled "Y" since no further action is needed. Exception: non-survivor duplicate-group members always show merge_into, not already_disabled.
	"""
	import re

	cutoff_date = frappe.utils.getdate(cutoff)

	# Bulk fetch all data
	counts_dict = count_links_for_all_customers()
	opp_summary = fetch_opportunity_summary()
	comm_counts = fetch_communication_counts()
	customers = frappe.get_all("Customer", fields=["name", "customer_name", "creation", "disabled"])
	distinct_pairs = decisions.load_distinct_pairs()

	# Exclude merge_from customers
	merge_from_set = {r["merge_from"] for r in decisions.load_customer_merges() if r.get("merge_from")}
	customers = [c for c in customers if c["name"] not in merge_from_set]

	# Classify each customer
	classifications: dict[str, tuple[str, str]] = {}
	link_totals: dict[str, int] = {}
	for customer in customers:
		name = customer["name"]
		link_counts = counts_dict.get(name, {})
		op_total = operational_link_total(link_counts)
		link_totals[name] = op_total

		opp = opp_summary.get(name)
		classifications[name] = classify_customer(link_counts, opp, customer["creation"], cutoff_date)

	# Build duplicate groups
	duplicate_groups = build_duplicate_groups(customers, classifications, link_totals, distinct_pairs)

	# Build rows
	rows = []
	for customer in customers:
		name = customer["name"]
		customer_name = customer.get("customer_name", "")
		creation = customer.get("creation", "")
		creation_date = str(creation).split(" ")[0] if creation else ""
		disabled = customer.get("disabled", 0)

		link_counts = counts_dict.get(name, {})
		op_total = link_totals[name]

		# link_breakdown: sorted labels with counts, marking suggestions
		breakdown_parts = []
		for label in sorted(link_counts.keys()):
			cnt = link_counts[label]
			if _is_suggestion_link(label):
				breakdown_parts.append(f"{label}:{cnt} (suggestion)")
			else:
				breakdown_parts.append(f"{label}:{cnt}")
		link_breakdown = "; ".join(breakdown_parts)

		# opportunity_breakdown
		opp = opp_summary.get(name)
		if opp and opp.get("stages"):
			opp_parts = [f"{stage}:{count}" for stage, count in sorted(opp["stages"].items())]
			opportunity_breakdown = "; ".join(opp_parts)
		else:
			opportunity_breakdown = ""

		# last_opportunity_date
		last_opp_date = opp.get("last_txn", "") if opp else ""

		# communication_count
		comm_count = comm_counts.get(name, 0)

		# duplicate group info
		group_info = duplicate_groups.get(name, {})
		duplicate_group = group_info.get("group_key", "")
		proposed_survivor = group_info.get("survivor", "")

		# proposed_action
		action, reason = classifications[name]
		if group_info and not group_info.get("is_survivor"):
			proposed_action = f"merge_into:{proposed_survivor}"
			confirm = ""
		elif disabled:
			# Customer is already disabled; no further action needed
			proposed_action = "already_disabled"
			confirm = "Y"
		else:
			proposed_action = action
			confirm = ""

		rows.append(
			{
				"name": name,
				"customer_name": customer_name,
				"creation": creation_date,
				"disabled": disabled,
				"operational_links": op_total,
				"link_breakdown": link_breakdown,
				"opportunity_breakdown": opportunity_breakdown,
				"last_opportunity_date": last_opp_date,
				"communication_count": comm_count,
				"duplicate_group": duplicate_group,
				"proposed_survivor": proposed_survivor,
				"proposed_action": proposed_action,
				"reason": reason,
				"confirm": confirm,
			}
		)

	# Sort: action rank (disable=0, merge_into=1, review=2, keep=3, already_disabled=4), then alphabetically within group/action, then name
	def _sort_key(row):
		action = row["proposed_action"]
		if action.startswith("merge_into:"):
			action_rank = 1
		else:
			action_rank = {"disable": 0, "review": 2, "keep": 3, "already_disabled": 4}.get(action, 3)
		group = row["duplicate_group"]
		name = row["name"]
		return (action_rank, group, name)

	rows.sort(key=_sort_key)

	# Write CSV
	site_path = frappe.get_site_path("private", "files")
	os.makedirs(site_path, exist_ok=True)
	path = os.path.join(site_path, f"customer_disposition_report_{frappe.utils.nowdate()}.csv")

	header = [
		"name",
		"customer_name",
		"creation",
		"disabled",
		"operational_links",
		"link_breakdown",
		"opportunity_breakdown",
		"last_opportunity_date",
		"communication_count",
		"duplicate_group",
		"proposed_survivor",
		"proposed_action",
		"reason",
		"confirm",
	]

	count = 0
	with open(path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=header)
		writer.writeheader()
		f.flush()
		os.fsync(f.fileno())

		for row in rows:
			writer.writerow(row)
			f.flush()
			os.fsync(f.fileno())
			count += 1

	print(f"Wrote {count} customer(s) to {path}")  # noqa: T201
	return path
