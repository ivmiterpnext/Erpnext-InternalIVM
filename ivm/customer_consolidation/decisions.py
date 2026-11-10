"""Loading and validating reviewed Customer-merge / iCorp-client-assignment decisions.

Decisions are tracked as version-controlled CSV files under ./decisions/, not as database
records, so the same reviewed list applies identically on every environment. Everything here
is pure except the two loader functions, which only read these local files.
"""

import codecs
import csv
import io
import json
import os
import tempfile

DECISIONS_DIR = os.path.join(os.path.dirname(__file__), "decisions")
CUSTOMER_MERGES_PATH = os.path.join(DECISIONS_DIR, "customer_merges.csv")
CLIENT_ASSIGNMENTS_PATH = os.path.join(DECISIONS_DIR, "icorp_client_assignments.csv")
CUSTOMER_DISTINCT_PAIRS_PATH = os.path.join(DECISIONS_DIR, "customer_distinct_pairs.csv")
CUSTOMERS_TO_CREATE_PATH = os.path.join(DECISIONS_DIR, "customers_to_create.csv")
CUSTOMERS_TO_DISABLE_PATH = os.path.join(DECISIONS_DIR, "customers_to_disable.csv")
RECORD_REASSIGNMENTS_PATH = os.path.join(DECISIONS_DIR, "record_reassignments.csv")
CUSTOMER_RENAMES_PATH = os.path.join(DECISIONS_DIR, "customer_renames.csv")

# (doctype, field) pairs record_reassignments.csv rows are allowed to touch. A ticket, warehouse
# request, or project filed under the wrong Customer at import time (e.g. a managing partner's
# name used instead of the end customer's) gets its one field corrected here, without merging
# the two Customers together the way customer_merges.csv does for genuine duplicates.
RECORD_REASSIGNMENT_FIELDS: dict[str, str] = {
	"Issue": "customer",
	"Warehouse Request": "account",
	"Project": "customer",
}


def _read_csv_rows(path: str) -> list[dict]:
	with open(path, encoding="utf-8-sig", newline="") as f:
		reader = csv.DictReader(f)
		return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _write_csv(path: str, header: list[str], rows: list[dict]) -> None:
	"""Write `rows` (each a dict with a subset of `header` as keys) to `path` as CSV, atomically
	(write to a temp file in the same directory, then os.replace). Missing keys in a row become
	empty cells."""
	fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
	try:
		with os.fdopen(fd, "w", newline="") as f:
			writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
			writer.writeheader()
			for row in rows:
				writer.writerow({k: row.get(k, "") for k in header})
		os.replace(temp_path, path)
	except BaseException:
		if os.path.exists(temp_path):
			os.remove(temp_path)
		raise


def load_customer_merges(path: str | None = None) -> list[dict]:
	"""Load customer_merges.csv. Skip rows where both merge_from and merge_into are empty."""
	rows = _read_csv_rows(path or CUSTOMER_MERGES_PATH)
	return [r for r in rows if r.get("merge_from") or r.get("merge_into")]


def load_client_assignments(path: str | None = None) -> list[dict]:
	"""Load icorp_client_assignments.csv. Skip rows where both client_id and customer are empty."""
	rows = _read_csv_rows(path or CLIENT_ASSIGNMENTS_PATH)
	return [r for r in rows if r.get("client_id") or r.get("customer")]


def load_distinct_pairs(path: str | None = None) -> set[frozenset]:
	"""Load customer_distinct_pairs.csv. Each row records two Customers confirmed to be
	different companies, even though their names look alike. Returned as a set of 2-element
	frozensets so lookups are order-independent."""
	rows = _read_csv_rows(path or CUSTOMER_DISTINCT_PAIRS_PATH)
	pairs: set[frozenset] = set()
	for row in rows:
		a = (row.get("customer_a") or "").strip()
		b = (row.get("customer_b") or "").strip()
		if a and b and a != b:
			pairs.add(frozenset({a, b}))
	return pairs


def load_customers_to_create(path: str | None = None) -> list[dict]:
	"""Load customers_to_create.csv. Skip rows with no customer_name. Each row is a Customer to
	create (by hand on dev via the "Create Customer..." button on iCorp Client Link, or on prod
	automatically via apply_on_migrate) before assignments are applied, so a Customer created only
	on one environment (e.g. by hand on dev) is reproduced on every other environment too."""
	rows = _read_csv_rows(path or CUSTOMERS_TO_CREATE_PATH)
	return [r for r in rows if r.get("customer_name")]


def load_record_reassignments(path: str | None = None) -> list[dict]:
	"""Load record_reassignments.csv. Skip rows with no doctype or name."""
	rows = _read_csv_rows(path or RECORD_REASSIGNMENTS_PATH)
	return [r for r in rows if r.get("doctype") and r.get("name")]


def _customer_reference_targets() -> list[tuple[str, tuple[str, ...]]]:
	"""(path, columns) for every decision CSV that stores a Customer name as a plain string. Built
	from the module-level path constants on each call (not at import time), so a test or caller
	that patches a path sees its patched value."""
	return [
		(CUSTOMER_MERGES_PATH, ("merge_into",)),
		(CLIENT_ASSIGNMENTS_PATH, ("customer",)),
		(CUSTOMER_DISTINCT_PAIRS_PATH, ("customer_a", "customer_b")),
		(RECORD_REASSIGNMENTS_PATH, ("from_customer", "to_customer")),
	]


def rewrite_customer_references(old: str, new: str, dry_run: bool = False) -> dict[str, int]:
	"""Repoint every string reference to Customer `old` in the decision CSVs that name Customers
	by string, from `old` to `new`. Covered columns (see _customer_reference_targets):
	  - customer_merges.csv: merge_into
	  - icorp_client_assignments.csv: customer
	  - customer_distinct_pairs.csv: customer_a, customer_b
	  - record_reassignments.csv: from_customer, to_customer
	Returns {filename: cells_changed}. With dry_run=True, only counts (nothing is written). Cells are
	matched after stripping whitespace; the file is otherwise round-tripped cell-for-cell (header,
	BOM, and row order preserved) and written atomically, and only if something changed. Note that
	customer_distinct_pairs rows are not re-sorted, which is harmless: load_distinct_pairs reads
	them as unordered frozensets."""
	counts: dict[str, int] = {}

	for path, columns in _customer_reference_targets():
		with open(path, "rb") as f:
			raw = f.read()
		has_bom = raw.startswith(codecs.BOM_UTF8)
		text = raw.decode("utf-8-sig")
		rows = list(csv.reader(io.StringIO(text, newline="")))
		header = rows[0]
		indexes = [header.index(c) for c in columns]

		changed = 0
		drop_indexes: set[int] = set()
		for row_no, row in enumerate(rows[1:], start=1):
			row_touched = False
			for idx in indexes:
				if len(row) > idx and row[idx].strip() == old:
					changed += 1
					row_touched = True
					if not dry_run:
						row[idx] = new
			# A merge_into repointed onto its own merge_from is a self-merge: the record it described
			# is now the same Customer, so the row carries no further action and would only be flagged
			# invalid by validate_customer_merges. Drop it (only customer_merges.csv has merge_from).
			if row_touched and columns == ("merge_into",) and row[0].strip() == new:
				drop_indexes.add(row_no)

		counts[os.path.basename(path)] = changed
		if not changed or dry_run:
			continue

		rows = [r for i, r in enumerate(rows) if i not in drop_indexes]
		buf = io.StringIO(newline="")
		csv.writer(buf).writerows(rows)
		payload = (codecs.BOM_UTF8 if has_bom else b"") + buf.getvalue().encode("utf-8")
		fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
		try:
			with os.fdopen(fd, "wb") as f:
				f.write(payload)
			os.replace(temp_path, path)
		except BaseException:
			if os.path.exists(temp_path):
				os.remove(temp_path)
			raise

	return counts


def load_customer_renames(path: str | None = None) -> list[dict]:
	"""Load customer_renames.csv. Skip rows with no current_name. Each row renames a Customer
	(via rename_customers_from_csv) once its status is "approved"; "needs_research" rows are
	kept in the file as a to-do record and never executed."""
	rows = _read_csv_rows(path or CUSTOMER_RENAMES_PATH)
	return [r for r in rows if r.get("current_name")]


def validate_record_reassignments(
	rows: list[dict], existing_customers: set[str], merge_map: dict[str, str]
) -> list[dict]:
	"""Pure. Return a copy of each row with added "errors" and "resolved_to_customer" keys.

	A to_customer being merged away is redirected to its merge target via merge_map — that's not
	an error. doctype/field must be one of RECORD_REASSIGNMENT_FIELDS's pairs; the field cell in
	the row is informational only (it's implied by doctype) but if present must match.
	"""
	seen: set[tuple[str, str]] = set()
	results = []

	for row in rows:
		doctype = (row.get("doctype") or "").strip()
		name = (row.get("name") or "").strip()
		field = (row.get("field") or "").strip()
		from_customer = (row.get("from_customer") or "").strip()
		to_customer = (row.get("to_customer") or "").strip()
		errors: list[str] = []

		expected_field = RECORD_REASSIGNMENT_FIELDS.get(doctype)
		resolved_to_customer = merge_map.get(to_customer, to_customer) if to_customer else ""

		if not doctype:
			errors.append("doctype is empty")
		elif expected_field is None:
			errors.append(f"doctype '{doctype}' is not allowed for record reassignment")
		elif field and field != expected_field:
			errors.append(f"field '{field}' does not match expected field '{expected_field}' for {doctype}")

		if not name:
			errors.append("name is empty")
		if not to_customer:
			errors.append("to_customer is empty")
		if to_customer and from_customer and to_customer == from_customer:
			errors.append("from_customer and to_customer are the same")
		if resolved_to_customer and resolved_to_customer not in existing_customers:
			errors.append(f"customer '{resolved_to_customer}' does not exist")

		if doctype and name:
			key = (doctype, name)
			if key in seen:
				errors.append(f"{doctype} '{name}' is listed more than once")
			else:
				seen.add(key)

		results.append(
			{
				**row,
				"errors": errors,
				"resolved_field": expected_field or field,
				"resolved_to_customer": resolved_to_customer,
			}
		)

	return results


def load_customers_to_disable(path: str | None = None) -> list[dict]:
	"""Load customers_to_disable.csv. Skip rows with no customer. Each row is a Customer a human
	has reviewed (via orphan_customers.report_orphan_customers) and decided to disable."""
	rows = _read_csv_rows(path or CUSTOMERS_TO_DISABLE_PATH)
	return [r for r in rows if r.get("customer")]


def parse_field_resolutions(raw: str | None) -> dict[str, str]:
	"""Parse a customer_merges.csv `field_resolutions` cell into a dict. Two formats are
	accepted: a JSON object (current format, written by save_merge_resolutions — handles any
	value, including ones containing ";" or "="), or the legacy "field=value; field2=value2"
	text format (still read for any older CSV rows). Blank/malformed entries are skipped rather
	than raising."""
	if not raw:
		return {}

	stripped = raw.strip()
	if stripped.startswith("{"):
		try:
			parsed = json.loads(stripped)
		except (json.JSONDecodeError, TypeError):
			return {}
		if not isinstance(parsed, dict):
			return {}
		return {str(k): str(v) for k, v in parsed.items() if k}

	result: dict[str, str] = {}
	for part in stripped.split(";"):
		part = part.strip()
		if not part or "=" not in part:
			continue
		field, _, value = part.partition("=")
		field = field.strip()
		if field:
			result[field] = value.strip()

	return result


def format_field_resolutions(resolutions: dict[str, str]) -> str:
	"""Pure. Inverse of parse_field_resolutions's JSON branch. Empty dict returns ""."""
	if not resolutions:
		return ""
	return json.dumps(resolutions, sort_keys=True, ensure_ascii=False)


def set_field_resolutions(
	rows: list[dict], merge_from: str, new_resolutions: dict[str, str], existing_customers: set[str]
) -> list[dict]:
	"""Pure. Returns a new list of customer_merges.csv rows with `merge_from`'s row updated:
	its existing field_resolutions are parsed, combined with new_resolutions (new values win),
	then written back as JSON. Only touches the row if merge_from still exists (i.e. the merge
	is still pending) — a resolution for an already-applied or nonexistent merge is a no-op.
	Rows for any other merge_from are returned unchanged."""
	if merge_from not in existing_customers:
		return rows

	result = []
	for row in rows:
		if (row.get("merge_from") or "").strip() != merge_from:
			result.append(row)
			continue
		existing = parse_field_resolutions(row.get("field_resolutions", ""))
		combined = {**existing, **new_resolutions}
		result.append({**row, "field_resolutions": format_field_resolutions(combined)})

	return result


def resolve_merge_map(merges: list[dict]) -> tuple[dict[str, str], set[str]]:
	"""Pure. Build from->into edges (first occurrence of a merge_from wins), follow chains to their
	final target, and detect cycles. Returns (merge_map_without_cycle_members, names_in_cycles)."""
	raw_edges: dict[str, str] = {}
	for row in merges:
		merge_from = (row.get("merge_from") or "").strip()
		merge_into = (row.get("merge_into") or "").strip()
		if not merge_from or not merge_into or merge_from == merge_into:
			continue
		if merge_from in raw_edges:
			continue
		raw_edges[merge_from] = merge_into

	resolved: dict[str, str] = {}
	cycle_members: set[str] = set()

	def resolve(name: str, seen: frozenset[str]) -> str | None:
		if name in resolved:
			return resolved[name]
		if name in seen:
			cycle_members.update(seen)
			cycle_members.add(name)
			return None

		seen = seen | {name}
		target = raw_edges[name]

		if target in raw_edges:
			final = resolve(target, seen)
		else:
			final = target

		if final is None:
			cycle_members.add(name)
			return None

		resolved[name] = final
		return final

	for start in list(raw_edges.keys()):
		resolve(start, frozenset())

	merge_map = {k: v for k, v in resolved.items() if k not in cycle_members}
	return merge_map, cycle_members


def validate_customer_merges(merges: list[dict], existing_customers: set[str]) -> list[dict]:
	"""Pure. Return a copy of each row with added "errors", "resolved_into", and "status" keys.

	"status" is one of:
	  - "pending": a genuine merge still to do
	  - "already_applied": merge_from is gone and merge_into exists — the merge already happened
	    (on this environment, or on whichever environment this decision file came from). Not an
	    error; the row stays in the file as a permanent record so every environment converges to
	    the same state, and running the merge again is simply skipped.
	  - "invalid": a genuine problem (missing name, cycle, duplicate, self-merge).
	"""
	merge_map, cycle_members = resolve_merge_map(merges)
	seen_from: set[str] = set()
	results = []

	for row in merges:
		merge_from = (row.get("merge_from") or "").strip()
		merge_into = (row.get("merge_into") or "").strip()
		errors: list[str] = []

		from_exists = merge_from in existing_customers
		into_exists = merge_into in existing_customers
		already_applied = bool(merge_from) and bool(merge_into) and not from_exists and into_exists

		if not merge_from:
			errors.append("merge_from is empty")
		if not merge_into:
			errors.append("merge_into is empty")
		if merge_from and merge_into and merge_from == merge_into:
			errors.append("merge_from and merge_into are the same")
		if merge_from and not from_exists and not already_applied:
			errors.append(f"merge_from '{merge_from}' does not exist")
		if merge_into and not into_exists:
			errors.append(f"merge_into '{merge_into}' does not exist")
		if merge_from:
			if merge_from in seen_from:
				errors.append(f"merge_from '{merge_from}' is listed more than once")
			else:
				seen_from.add(merge_from)
		if merge_from and merge_from in cycle_members:
			errors.append(f"'{merge_from}' is part of a merge cycle")

		resolved_into = merge_map.get(merge_from, "") if merge_from else ""

		if errors:
			status = "invalid"
		elif already_applied:
			status = "already_applied"
		else:
			status = "pending"

		results.append({**row, "errors": errors, "resolved_into": resolved_into, "status": status})

	return results


def validate_client_assignments(
	assignments: list[dict],
	existing_customers: set[str],
	icorp_client_ids: set[str],
	merge_map: dict[str, str],
) -> list[dict]:
	"""Pure. Return a copy of each row with added "errors" and "resolved_customer" keys.

	A customer being merged away is redirected to its merge target via merge_map — that's not an error.
	"""
	seen_ids: set[str] = set()
	results = []

	for row in assignments:
		client_id = (row.get("client_id") or "").strip()
		customer = (row.get("customer") or "").strip()
		errors: list[str] = []
		resolved_customer = merge_map.get(customer, customer) if customer else ""

		if not client_id:
			errors.append("client_id is empty")
		if not customer:
			errors.append("customer is empty")
		if client_id and client_id not in icorp_client_ids:
			errors.append(f"iCorp client {client_id} does not exist")
		if resolved_customer and resolved_customer not in existing_customers:
			errors.append(f"customer '{resolved_customer}' does not exist")
		if client_id:
			if client_id in seen_ids:
				errors.append(f"client_id {client_id} is listed more than once")
			else:
				seen_ids.add(client_id)

		results.append({**row, "errors": errors, "resolved_customer": resolved_customer})

	return results


def is_pending_sync_only(errors: list[str]) -> bool:
	"""True if every error on a validated assignment row is exactly the
	'iCorp client {id} does not exist' kind -- i.e. this environment's iCorp
	Client Link table simply doesn't have that client yet (it may sync from a
	different iCorp environment than the one the CSV's data came from, or the
	client may be newly created and not yet picked up by the daily sync). Any
	OTHER error on the same row (bad customer target, duplicate client_id,
	empty fields) means this is a genuine data problem, not just pending sync."""
	return bool(errors) and all(
		e.startswith("iCorp client ") and e.endswith(" does not exist") for e in errors
	)


def apply_merge_map(
	project_rows: list[dict],
	existing_customer_icorp_ids: dict[str, str],
	customers: list[dict],
	merge_map: dict[str, str],
) -> tuple[list[dict], dict[str, str], list[dict]]:
	"""Pure, returns new structures without mutating the inputs.

	Customer docnames that are being merged away are renamed to their target in the returned
	`customers` list, but `customer_name` is left as-is — it still identifies the merged record for
	name-matching evidence, it just now resolves to the surviving docname.
	"""
	new_project_rows = []
	for row in project_rows:
		new_row = dict(row)
		customer = new_row.get("customer")
		if customer in merge_map:
			new_row["customer"] = merge_map[customer]
		new_project_rows.append(new_row)

	new_existing_ids = {
		client_id: merge_map.get(customer, customer)
		for client_id, customer in existing_customer_icorp_ids.items()
	}

	new_customers = []
	for customer in customers:
		new_customer = dict(customer)
		if new_customer.get("name") in merge_map:
			new_customer["name"] = merge_map[new_customer["name"]]
		new_customers.append(new_customer)

	return new_project_rows, new_existing_ids, new_customers


def compute_review_status(
	customer: str | None,
	proposed_customer: str | None,
	rows: list[dict],
	existing_customers: set[str],
) -> str:
	"""Pure. `rows` is a list of {"customer": str, "role": str} dicts (the Related Customers
	child rows, in whatever order). Returns one of:
	  "Needs match"        - no assigned customer, no row marked "This client's Customer",
	                          and no proposed_customer to fall back on
	  "Merge pending"       - some row is marked "Duplicate - merge in", its customer still
	                          exists, and it isn't the anchor itself
	  "Possible duplicates" - some row has no decision ("") and its customer isn't the anchor
	  "Ready to accept"     - no customer assigned yet, but there's an anchor and nothing
	                          else open
	  "Done"                - a customer is assigned and nothing else is open
	Anchor = the row marked "This client's Customer", else `customer`, else `proposed_customer`.
	"""
	customer = customer or ""
	proposed_customer = proposed_customer or ""

	anchor = ""
	for row in rows:
		if row.get("role") == "This client's Customer":
			anchor = row.get("customer") or ""
			break
	if not anchor:
		anchor = customer or proposed_customer

	if not anchor:
		return "Needs match"

	for row in rows:
		row_customer = row.get("customer") or ""
		if row.get("role") == "Duplicate - merge in" and row_customer and row_customer != anchor:
			if row_customer in existing_customers:
				return "Merge pending"

	for row in rows:
		row_customer = row.get("customer") or ""
		if not row.get("role") and row_customer and row_customer != anchor:
			return "Possible duplicates"

	if not customer:
		return "Ready to accept"

	return "Done"


def upsert_client_assignment(
	rows: list[dict], client_id: str, customer: str, evidence: str = ""
) -> list[dict]:
	"""Pure. `rows` is the full icorp_client_assignments.csv content (list of
	{"client_id", "customer", "evidence"} dicts). Returns a new list with this client_id's row
	replaced (or removed, if `customer` is empty) or appended."""
	kept = [r for r in rows if (r.get("client_id") or "").strip() != client_id]
	if customer:
		kept.append({"client_id": client_id, "customer": customer, "evidence": evidence})
	return kept


def upsert_client_merges(
	rows: list[dict], client_id: str, desired_pairs: list[tuple[str, str]], existing_customers: set[str]
) -> list[dict]:
	"""Pure. `rows` is the full customer_merges.csv content (dicts with merge_from, merge_into,
	evidence, merge_considerations, field_resolutions, source_client_id). `desired_pairs` is a
	list of (merge_from, merge_into) this client_id wants right now.

	- Rows from other client_ids, or already-applied rows (merge_from no longer exists) from
	  this client_id, are kept untouched.
	- This client_id's still-pending rows (merge_from exists) that aren't in desired_pairs are
	  dropped.
	- desired_pairs not already present (from any source) are appended, source_client_id=client_id.
	- Raises ValueError if a desired merge_from is already listed (from any source, pending) with
	  a different merge_into, or if applying the result would create a cycle (via resolve_merge_map).
	"""
	desired_froms = {pair[0] for pair in desired_pairs}
	desired_map = dict(desired_pairs)

	kept: list[dict] = []
	existing_from_this_client_still_pending = set()

	for row in rows:
		merge_from = (row.get("merge_from") or "").strip()
		source = (row.get("source_client_id") or "").strip()
		still_pending = merge_from in existing_customers

		if source == client_id and still_pending:
			existing_from_this_client_still_pending.add(merge_from)
			if merge_from in desired_froms:
				kept.append(row)
			# else: dropped — no longer wanted by this client
			continue

		# Not from this client, or already applied — always kept, but check for conflicts
		if merge_from in desired_froms and still_pending:
			existing_into = (row.get("merge_into") or "").strip()
			if existing_into != desired_map[merge_from]:
				raise ValueError(
					f"'{merge_from}' is already listed to merge into '{existing_into}', "
					f"can't also merge it into '{desired_map[merge_from]}'"
				)
		kept.append(row)

	for merge_from, merge_into in desired_pairs:
		if merge_from in existing_from_this_client_still_pending:
			continue
		already_listed = any(
			(r.get("merge_from") or "").strip() == merge_from
			and (r.get("merge_into") or "").strip() == merge_into
			for r in kept
		)
		if already_listed:
			continue
		kept.append(
			{
				"merge_from": merge_from,
				"merge_into": merge_into,
				"evidence": "",
				"merge_considerations": "",
				"field_resolutions": "",
				"source_client_id": client_id,
			}
		)

	_, cycle_members = resolve_merge_map(kept)
	bad = cycle_members & desired_froms
	if bad:
		raise ValueError(f"Merging {sorted(bad)} would create a cycle")

	return kept


def upsert_distinct_pairs(
	rows: list[dict], client_id: str, anchor: str, dismissed_customers: list[str]
) -> list[dict]:
	"""Pure. `rows` is the full customer_distinct_pairs.csv content (dicts with customer_a,
	customer_b, client_id, note). Replaces every row previously written by this client_id with
	one row per (anchor, dismissed) pair, sorted so customer_a < customer_b."""
	kept = [r for r in rows if (r.get("client_id") or "").strip() != client_id]
	for dismissed in dismissed_customers:
		if not dismissed or dismissed == anchor:
			continue
		a, b = sorted((anchor, dismissed))
		kept.append({"customer_a": a, "customer_b": b, "client_id": client_id, "note": ""})
	return kept


def upsert_customer_to_create(rows: list[dict], customer_name: str, fields: dict) -> list[dict]:
	"""Pure. `rows` is the full customers_to_create.csv content (dicts with customer_name,
	customer_type, customer_group, territory, source_client_id, note). Replaces the row for
	`customer_name` if one exists, otherwise appends it."""
	kept = [r for r in rows if (r.get("customer_name") or "").strip() != customer_name]
	kept.append({"customer_name": customer_name, **fields})
	return kept


def append_customer_merges(
	rows: list[dict], new_rows: list[dict], existing_customers: set[str]
) -> tuple[list[dict], list[dict]]:
	"""Pure. Append new merge rows to the existing customer_merges.csv content.

	Args:
		rows: full current customer_merges.csv content (list of dicts with full header)
		new_rows: list of dicts to append (at least merge_from, merge_into, evidence; optionally merge_considerations, field_resolutions, source_client_id)
		existing_customers: set of customer names that currently exist

	Returns (updated_rows, skipped) where skipped is a list of {"merge_from":..., "merge_into":..., "reason": "duplicate pair"} for new_rows whose (merge_from, merge_into) pair already exists.

	Raises ValueError if a new_row's merge_from is already present in rows with a DIFFERENT merge_into (pending status).
	Raises ValueError if the result would create a merge cycle.
	"""
	skipped = []

	# Check for duplicate pairs and conflicting merge_into
	existing_pairs = {
		(r.get("merge_from", "").strip(), r.get("merge_into", "").strip())
		for r in rows
		if r.get("merge_from") and r.get("merge_into")
	}
	existing_from_map = {
		r.get("merge_from", "").strip(): r.get("merge_into", "").strip()
		for r in rows
		if r.get("merge_from") and r.get("merge_into")
	}

	to_append = []
	for new_row in new_rows:
		merge_from = (new_row.get("merge_from") or "").strip()
		merge_into = (new_row.get("merge_into") or "").strip()

		if not merge_from or not merge_into:
			continue

		# Check for duplicate pair
		if (merge_from, merge_into) in existing_pairs:
			skipped.append({"merge_from": merge_from, "merge_into": merge_into, "reason": "duplicate pair"})
			continue

		# Check for conflicting merge_into (same merge_from, different merge_into, still pending)
		if merge_from in existing_from_map and merge_from in existing_customers:
			existing_into = existing_from_map[merge_from]
			if existing_into != merge_into:
				raise ValueError(
					f"'{merge_from}' is already listed to merge into '{existing_into}', "
					f"can't also merge it into '{merge_into}'"
				)

		# Fill in optional fields with defaults
		to_append.append(
			{
				"merge_from": merge_from,
				"merge_into": merge_into,
				"evidence": new_row.get("evidence", ""),
				"merge_considerations": new_row.get("merge_considerations", ""),
				"field_resolutions": new_row.get("field_resolutions", ""),
				"source_client_id": new_row.get("source_client_id", ""),
			}
		)

	# Combine and check for cycles
	combined = rows + to_append
	_, cycle_members = resolve_merge_map(combined)

	# Check if any of the new_rows' merge_from values are in cycles
	new_from_set = {(r.get("merge_from") or "").strip() for r in to_append}
	bad = cycle_members & new_from_set
	if bad:
		raise ValueError(f"Merging {sorted(bad)} would create a cycle")

	return combined, skipped


def upsert_customers_to_disable(rows: list[dict], new_rows: list[dict]) -> list[dict]:
	"""Pure. Append new rows to customers_to_disable.csv, skipping any whose customer is already present.

	Args:
		rows: full current customers_to_disable.csv content
		new_rows: list of dicts with customer, reason, decided_by, date_decided

	Returns combined list with new_rows appended (skipping duplicates by customer name).
	"""
	existing_customers = {(r.get("customer") or "").strip() for r in rows if r.get("customer")}

	kept = list(rows)
	for new_row in new_rows:
		customer = (new_row.get("customer") or "").strip()
		if customer and customer not in existing_customers:
			kept.append(new_row)
			existing_customers.add(customer)

	return kept
