"""Applies reviewed Customer-consolidation decisions: syncs the iCorp client list, executes
confirmed merges, applies confirmed client-to-Customer assignments, and sets each Customer's
master iCorp client where it's unambiguous.

Entry points:
  - run_apply_decisions(execute=False): manual, via `bench execute`. Defaults to a read-only
    preview.
  - apply_on_migrate(): hooked via `after_migrate`. Skips entirely if the decision files haven't
    changed since the last successful run (tracked via a content hash in a Default Value). Logs
    and continues on failure rather than blocking the migrate.

Execution of merges/assignments only ever acts on "pending" rows — anything already applied or
invalid is skipped, which is what makes re-running this safe on every environment.
"""

import hashlib
import time

import frappe
from frappe.model.rename_doc import rename_doc as _rename_doc

from ivm.customer_consolidation import decisions, merge_analysis, orphan_customers
from ivm.customer_consolidation.dry_run import (
	build_client_customer_matches,
	build_customer_coverage,
	fetch_icorp_clients,
	gather_customers,
	gather_existing_customer_icorp_ids,
	gather_project_rows,
	normalize_customer_name,
)
from ivm.deployments.patches.backfill_project_icorp_client import run_backfill

_STOPWORDS = frozenset({"the", "of", "and"})
_FIRST_TOKEN_MAX_FREQUENCY = 10
_JACCARD_MIN = 0.5
_MAX_NAME_CANDIDATES = 10

_APPLIED_HASH_KEY = "customer_consolidation_applied_hash"


def _icorp_is_configured() -> bool:
	"""True if this site has iCorp API credentials configured at all (site_config or
	environment variable). Used to let apply_on_migrate skip cleanly, rather than
	fail the migrate, on a site that was never set up to run this -- e.g. test.local,
	which shares ivm's codebase with dev.local but has no iCorp credentials of its
	own and isn't meant to run the consolidation."""
	from ivm.integrations.keyvault import get_config_value

	return bool(get_config_value("AZURE_KEYVAULT_URL")) and bool(get_config_value("ICORP_API_BASE_URL"))


# Child tables on Customer whose rows Frappe's merge would otherwise silently delete along with
# the losing record (it deletes the losing doc's own rows, it doesn't move them). Carried over to
# the survivor, skipping any row that already has an equivalent on the survivor's side.
_CHILD_TABLES_TO_CARRY_OVER = ("accounts", "sales_team", "credit_limits", "companies")


def create_missing_customers(dry_run: bool = False) -> list[dict]:
	"""Create every Customer listed in customers_to_create.csv that doesn't already exist, so a
	Customer created by hand on one environment (e.g. via the "Create Customer..." button on
	iCorp Client Link on dev) is reproduced identically everywhere else, including a fresh prod
	restore of dev or prod's own first migrate after the CSV is deployed. A row whose Customer
	Group or Territory is missing or doesn't exist falls back to this org's conventional defaults
	("Commercial" / "All Territories") rather than being reported as invalid. A Customer Group that
	exists but is a Group-type node (is_group=1, e.g. "All Customer Groups" itself) is reported as
	"invalid" instead of falling back, since ERPNext's own Customer.validate_customer_group() rejects
	assigning a Group-type node directly -- letting that reach .insert() would raise uncaught."""
	rows = decisions.load_customers_to_create()
	results = []

	for row in rows:
		customer_name = row["customer_name"]

		if frappe.db.exists("Customer", customer_name):
			results.append({"customer_name": customer_name, "action": "exists"})
			continue

		customer_group = row.get("customer_group") or ""
		if customer_group and frappe.db.get_value("Customer Group", customer_group, "is_group"):
			results.append(
				{
					"customer_name": customer_name,
					"action": "invalid",
					"reason": f"Customer Group '{customer_group}' is a Group-type node",
				}
			)
			continue
		if not customer_group or not frappe.db.exists("Customer Group", customer_group):
			customer_group = "Commercial"

		territory = row.get("territory") or ""
		if not territory or not frappe.db.exists("Territory", territory):
			territory = "All Territories"

		if dry_run:
			results.append({"customer_name": customer_name, "action": "would_create"})
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": customer_name,
				"customer_type": row.get("customer_type") or "Company",
				"customer_group": customer_group,
				"territory": territory,
			}
		).insert(ignore_permissions=True)

		if doc.name != customer_name:
			results.append(
				{
					"customer_name": customer_name,
					"action": "name_mismatch",
					"created_as": doc.name,
				}
			)
		else:
			results.append({"customer_name": customer_name, "action": "created"})

	if not dry_run:
		frappe.db.commit()

	return results


def sync_icorp_client_links() -> dict:
	"""Upsert identity fields (name, active, parent) for every iCorp client. Never touches
	customer / assignment_source / proposed_customer / match_status / match_evidence — those are
	Frappe-side decisions, not iCorp data."""
	clients = fetch_icorp_clients()
	created, updated = 0, 0

	for client in clients:
		client_id = str(client["id"])
		display_label = f"({client_id}) {client.get('name') or ''}".strip()
		values = {
			"client_name": client.get("name") or "",
			"display_label": display_label,
			"is_active": 1 if client.get("is_active") else 0,
			"is_partner_client": 1 if client.get("is_partner_client") else 0,
			"sv_location_count_active": client.get("sv_location_count_active") or 0,
			"sv_machine_count_active": client.get("sv_machine_count_active") or 0,
		}

		if frappe.db.exists("iCorp Client Link", client_id):
			frappe.db.set_value("iCorp Client Link", client_id, values)
			updated += 1
		else:
			doc = frappe.get_doc({"doctype": "iCorp Client Link", "icorp_client_id": client_id, **values})
			doc.insert(ignore_permissions=True)
			created += 1

	# second pass: parent links, once every client row exists
	for client in clients:
		parent_id = client.get("partner_client_id")
		client_id = str(client["id"])
		parent_value = str(parent_id) if parent_id else ""
		if parent_value and not frappe.db.exists("iCorp Client Link", parent_value):
			parent_value = ""  # defensive: shouldn't happen, but don't link to a non-existent row
		frappe.db.set_value("iCorp Client Link", client_id, "parent_client", parent_value)

	frappe.db.commit()
	return {"total": len(clients), "created": created, "updated": updated}


def _icorp_client_links_as_dicts() -> list[dict]:
	"""Build the icorp_clients-shaped list build_client_customer_matches expects, from the
	currently stored iCorp Client Link records rather than a fresh iCorp API call."""
	rows = frappe.get_all(
		"iCorp Client Link",
		fields=["icorp_client_id", "client_name", "is_active", "is_partner_client", "parent_client"],
	)
	name_by_id = {r["icorp_client_id"]: r["client_name"] for r in rows}

	return [
		{
			"id": row["icorp_client_id"],
			"name": row["client_name"],
			"is_active": row["is_active"],
			"is_partner_client": row["is_partner_client"],
			"partner_client_id": row["parent_client"] or None,
			"partner_client_name": name_by_id.get(row["parent_client"]) if row["parent_client"] else None,
		}
		for row in rows
	]


def _build_name_candidate_index(customers: list[dict]) -> dict:
	"""Build two indexes over normalized Customer names, used by _find_name_candidates:
	  "tokens": {customer_name: [list of normalized words, stopwords removed]}
	  "first_token": {word: set of customer_names whose first normalized word is `word`}
	Not used to auto-resolve anything — only to surface suggestions for a human to review."""
	tokens_by_customer: dict[str, list[str]] = {}
	first_token_index: dict[str, set[str]] = {}

	for customer in customers:
		name = customer.get("customer_name")
		if not name:
			continue
		words = [w for w in normalize_customer_name(name).split() if w not in _STOPWORDS]
		if not words:
			continue
		tokens_by_customer[customer["name"]] = words
		first_token_index.setdefault(words[0], set()).add(customer["name"])

	return {"tokens": tokens_by_customer, "first_token": first_token_index}


def _build_customer_activity_counts() -> dict[str, dict[str, int]]:
	"""Project + Issue counts per Customer, kept separate so they can both be shown (e.g.
	"11 Projects, 265 Issues") and summed for ranking. One pass each over Project and Issue
	rather than a per-candidate query."""
	counts: dict[str, dict[str, int]] = {}
	for doctype, key in (("Project", "projects"), ("Issue", "issues")):
		for row in frappe.get_all(doctype, filters={"customer": ["!=", ""]}, fields=["customer"]):
			counts.setdefault(row["customer"], {"projects": 0, "issues": 0})
			counts[row["customer"]][key] += 1
	return counts


def _format_activity_summary(customer: str, activity_counts: dict[str, dict[str, int]]) -> str:
	counts = activity_counts.get(customer, {"projects": 0, "issues": 0})
	return f"{counts['projects']} Projects, {counts['issues']} Issues"


def _find_name_candidates(
	client_name: str, index: dict, activity_counts: dict[str, dict[str, int]], exclude: set[str]
) -> list[str]:
	"""Loose, informational-only suggestions: Customers whose name resembles the client's name,
	by either of two rules —
	  1. the Customer's first normalized word matches the client's first normalized word, and
	     that word isn't too generic (starts at most _FIRST_TOKEN_MAX_FREQUENCY Customer names)
	  2. at least half the normalized words are shared between the two names (Jaccard >= 0.5)
	Ranked by how active the Customer is. Not used to auto-resolve anything."""
	words = [w for w in normalize_customer_name(client_name).split() if w not in _STOPWORDS]
	if not words:
		return []

	tokens_by_customer = index["tokens"]
	first_token_index = index["first_token"]
	word_set = set(words)

	candidates: set[str] = set()

	first_word_matches = first_token_index.get(words[0], set())
	if len(first_word_matches) <= _FIRST_TOKEN_MAX_FREQUENCY:
		candidates |= first_word_matches

	for customer_name, customer_words in tokens_by_customer.items():
		customer_word_set = set(customer_words)
		union = word_set | customer_word_set
		if union and len(word_set & customer_word_set) / len(union) >= _JACCARD_MIN:
			candidates.add(customer_name)

	candidates -= exclude

	def _activity_total(customer: str) -> int:
		counts = activity_counts.get(customer, {})
		return counts.get("projects", 0) + counts.get("issues", 0)

	ranked = sorted(candidates, key=lambda c: -_activity_total(c))
	return ranked[:_MAX_NAME_CANDIDATES]


def _set_related_customers(
	client_id: str,
	candidate_customers: list[str],
	proposed_customer: str,
	activity_counts: dict[str, dict[str, int]],
	evidence_by_customer: dict[str, str] | None = None,
	distinct_pairs: set | None = None,
) -> None:
	"""Rebuild the Related Customers child table for one client: every Customer the evidence
	points at (tagged with why), plus the proposed customer, plus loose name-candidates. Any
	`role` a human already picked is carried over by matching on customer name, so a routine
	refresh never erases a pending decision. A candidate with no existing decision gets
	pre-marked "Different company" if it's a stored distinct pair against the anchor (the
	proposed customer, here, since this runs before a customer is assigned).

	Writes child rows directly (delete + db_insert) rather than loading and saving the full
	parent document, since this runs for up to ~1,400 clients per refresh. `activity_counts` is
	computed once by the caller and passed in — never recomputed per client.
	"""
	evidence_by_customer = evidence_by_customer or {}
	distinct_pairs = distinct_pairs or set()

	existing_roles = {
		r["customer"]: r["role"]
		for r in frappe.get_all(
			"iCorp Client Link Customer Candidate",
			filters={"parent": client_id, "parenttype": "iCorp Client Link"},
			fields=["customer", "role"],
		)
	}

	frappe.db.delete(
		"iCorp Client Link Customer Candidate", {"parent": client_id, "parenttype": "iCorp Client Link"}
	)

	ordered_customers: list[str] = []
	seen: set[str] = set()
	for customer in (
		([proposed_customer] if proposed_customer else [])
		+ list(evidence_by_customer.keys())
		+ candidate_customers
	):
		if customer and customer not in seen:
			seen.add(customer)
			ordered_customers.append(customer)

	anchor = proposed_customer or ""

	for idx, customer in enumerate(ordered_customers, start=1):
		role = existing_roles.get(customer, "")
		if not role and anchor and customer != anchor and frozenset({anchor, customer}) in distinct_pairs:
			role = "Different company"

		evidence_label = evidence_by_customer.get(
			customer, "Similar name" if customer != proposed_customer else "Assigned"
		)
		if customer == proposed_customer and customer in evidence_by_customer:
			evidence_label = evidence_by_customer[customer]

		frappe.get_doc(
			{
				"doctype": "iCorp Client Link Customer Candidate",
				"parent": client_id,
				"parenttype": "iCorp Client Link",
				"parentfield": "related_customers",
				"idx": idx,
				"customer": customer,
				"is_current_proposal": 1 if customer == proposed_customer else 0,
				"evidence": evidence_label,
				"activity_summary": _format_activity_summary(customer, activity_counts),
				"role": role,
			}
		).db_insert()


def _build_active_duplicate_name_index(icorp_clients: list[dict]) -> dict[str, list[tuple[str, str]]]:
	"""Maps a lowercased client name to every ACTIVE iCorp client (id, display info) sharing that
	exact name. An inactive duplicate isn't a live naming collision worth warning about — it's
	historical, nothing currently needs assigning against it."""
	index: dict[str, list[tuple[str, str]]] = {}
	for client in icorp_clients:
		if not client.get("is_active"):
			continue
		name_key = (client.get("name") or "").strip().lower()
		if name_key:
			index.setdefault(name_key, []).append(client["id"])
	return index


def refresh_match_proposals() -> dict:
	"""Recompute proposed_customer / match_status / match_evidence for every iCorp Client Link,
	from current Project/Customer data. Never touches the `customer` field itself — that's always
	a human or a prior decision, never overwritten by a routine refresh.

	Also overlays a "partner_suspect" status: when a client's only evidence is Project usage that
	happens to match its iCorp parent's own Customer, the Project almost certainly named the
	managing partner rather than the end customer (see the Zones/Microsoft/Altria case). Detected
	rows get their proposal cleared — same principle as a conflict — rather than silently proposing
	the partner.
	"""
	icorp_clients = _icorp_client_links_as_dicts()
	project_rows = gather_project_rows()
	existing_customer_icorp_ids = gather_existing_customer_icorp_ids()
	customers = gather_customers()

	matches = build_client_customer_matches(
		icorp_clients, project_rows, existing_customer_icorp_ids, customers
	)
	matches_by_id = {row["client_id"]: row for row in matches}

	name_candidate_index = _build_name_candidate_index(customers)
	activity_counts = _build_customer_activity_counts()
	active_duplicate_name_index = _build_active_duplicate_name_index(icorp_clients)
	distinct_pairs = decisions.load_distinct_pairs()

	refreshed = 0
	for row in matches:
		client_id = row["client_id"]
		status = row["status"]
		proposed_customer = row["proposed_customer"] or ""
		parent_id = row["parent_client_id"]

		# A Link's `customer` can be set through a path other than "Accept proposal"
		# (e.g. the bulk customers_to_create.csv/icorp_client_assignments.csv flow).
		# When that happens while the matcher's own status is conflict/unmatched (so
		# `proposed_customer` stays blank), `anchor_customer` must still reflect the
		# real assigned customer — otherwise the distinct-pairs lookup below silently
		# misses every dismissal recorded against that customer.
		assigned_customer = frappe.db.get_value("iCorp Client Link", client_id, "customer") or ""
		anchor_customer = assigned_customer or proposed_customer

		parent_customer = ""
		if parent_id:
			parent_customer = frappe.db.get_value("iCorp Client Link", parent_id, "customer") or ""
			if not parent_customer:
				parent_row = matches_by_id.get(parent_id)
				if parent_row:
					parent_customer = parent_row["proposed_customer"] or ""

		own_name_matches = set(row["_exact_name_customers"]) | set(row["_fuzzy_name_customers"])
		is_partner_suspect = (
			status == "project_only"
			and parent_customer
			and proposed_customer == parent_customer
			and proposed_customer not in own_name_matches
		)

		if is_partner_suspect:
			status = "partner_suspect"
			proposed_customer = ""

		evidence_by_customer: dict[str, str] = {}
		for c, n in row["_project_customer_counts"].items():
			evidence_by_customer[c] = f"Projects ({n})"
		if row["existing_field_customer"]:
			evidence_by_customer.setdefault(row["existing_field_customer"], "Legacy field")
		for c in row["_exact_name_customers"]:
			evidence_by_customer.setdefault(c, "Exact name")
		for c in row["_fuzzy_name_customers"]:
			evidence_by_customer.setdefault(c, "Similar name")

		exclude = set(own_name_matches) | ({anchor_customer} if anchor_customer else set())
		candidates = _find_name_candidates(row["client_name"], name_candidate_index, activity_counts, exclude)
		_set_related_customers(
			client_id,
			candidates,
			anchor_customer,
			activity_counts,
			evidence_by_customer=evidence_by_customer,
			distinct_pairs=distinct_pairs,
		)

		related_rows = frappe.get_all(
			"iCorp Client Link Customer Candidate",
			filters={"parent": client_id, "parenttype": "iCorp Client Link"},
			fields=["customer", "role"],
		)
		existing_customers_set = {c["name"] for c in customers}
		review_status = decisions.compute_review_status(
			assigned_customer,
			proposed_customer,
			related_rows,
			existing_customers_set,
		)
		has_multiple_candidates = 1 if len(related_rows) > 1 else 0

		name_key = (row["client_name"] or "").strip().lower()
		siblings = [
			sibling_id
			for sibling_id in active_duplicate_name_index.get(name_key, [])
			if sibling_id != client_id
		]

		evidence_parts = []
		if row["project_customers"]:
			evidence_parts.append(f"Projects: {row['project_customers']}")
		if row["existing_field_customer"]:
			evidence_parts.append(f"Existing field: {row['existing_field_customer']}")
		if row["exact_name_customers"]:
			evidence_parts.append(f"Exact name match: {row['exact_name_customers']}")
		if row["fuzzy_name_customers"]:
			evidence_parts.append(f"Fuzzy name match: {row['fuzzy_name_customers']}")
		if is_partner_suspect:
			evidence_parts.append(
				f"Only evidence is Project usage matching the iCorp parent's own Customer "
				f"('{parent_customer}') — likely the managing partner, not the end customer"
			)

		frappe.db.set_value(
			"iCorp Client Link",
			client_id,
			{
				"proposed_customer": proposed_customer,
				"match_status": status,
				"parent_customer": parent_customer,
				"match_evidence": "; ".join(evidence_parts),
				"has_multiple_customer_candidates": has_multiple_candidates,
				"duplicate_name_siblings": ", ".join(siblings),
				"review_status": review_status,
			},
		)
		refreshed += 1

	frappe.db.commit()
	return {"refreshed": refreshed}


def _linked_counts(customer: str) -> dict:
	return {
		"contacts": frappe.db.count(
			"Dynamic Link", {"link_doctype": "Customer", "link_name": customer, "parenttype": "Contact"}
		),
		"addresses": frappe.db.count(
			"Dynamic Link", {"link_doctype": "Customer", "link_name": customer, "parenttype": "Address"}
		),
		"projects": frappe.db.count("Project", {"customer": customer}),
		"issues": frappe.db.count("Issue", {"customer": customer}),
	}


def _carry_over_child_tables(merge_from: str, merge_into: str) -> list[str]:
	"""Copy child-table rows Frappe's merge would otherwise delete with the losing record. Skips
	rows that look like an exact duplicate of one already on the survivor (same values across all
	non-system fields). Returns a list of 'table:n' strings for rows actually carried over."""
	carried = []
	customer_meta = frappe.get_meta("Customer")

	for fieldname in _CHILD_TABLES_TO_CARRY_OVER:
		field = customer_meta.get_field(fieldname)
		if not field or field.fieldtype not in ("Table", "Table MultiSelect"):
			continue
		child_doctype = field.options

		from_rows = frappe.get_all(
			child_doctype, filters={"parent": merge_from, "parenttype": "Customer"}, fields=["*"]
		)
		if not from_rows:
			continue

		into_rows = frappe.get_all(
			child_doctype, filters={"parent": merge_into, "parenttype": "Customer"}, fields=["*"]
		)
		skip_fields = {
			"name",
			"parent",
			"parentfield",
			"parenttype",
			"idx",
			"owner",
			"creation",
			"modified",
			"modified_by",
			"docstatus",
		}
		into_signatures = {
			tuple(sorted((k, v) for k, v in row.items() if k not in skip_fields)) for row in into_rows
		}

		survivor = frappe.get_doc("Customer", merge_into)
		moved_count = 0
		for row in from_rows:
			signature = tuple(sorted((k, v) for k, v in row.items() if k not in skip_fields))
			if signature in into_signatures:
				continue
			new_row = {k: v for k, v in row.items() if k not in skip_fields}
			survivor.append(fieldname, new_row)
			moved_count += 1

		if moved_count:
			survivor.save(ignore_permissions=True)
			carried.append(f"{fieldname}:{moved_count}")

	return carried


def disable_decided_customers(dry_run: bool = True) -> list[dict]:
	"""Soft-deletes (disabled=1) every Customer in customers_to_disable.csv. The CSV is the reviewed
	decision, so it's applied as-is: a Customer that has operational links (Issues, Projects,
	Warehouse Requests...) is still disabled, and reported as action "disabled_with_links" (or
	"would_disable_with_links" on dry run) for visibility -- not skipped, and not treated as a
	problem. Disabling never touches linked records; ERPNext only blocks a disabled Customer on new
	accounting documents.

	Skips Customers that no longer exist (already merged/deleted), are already disabled, or are a
	pending merge_from in customer_merges.csv (the merge workflow handles those).

	Link counts come from one bulk pass (orphan_customers.count_links_for_all_customers), not a
	per-Customer count -- the per-row version took ~3s per Customer, i.e. hours for thousands of rows."""
	merge_from_set = {r["merge_from"] for r in decisions.load_customer_merges() if r.get("merge_from")}
	rows = decisions.load_customers_to_disable()
	counts = orphan_customers.count_links_for_all_customers() if rows else {}

	results = []

	for row in rows:
		customer = row["customer"]

		if not frappe.db.exists("Customer", customer):
			results.append({"customer": customer, "action": "already_gone"})
			continue

		if frappe.db.get_value("Customer", customer, "disabled"):
			results.append({"customer": customer, "action": "already_disabled"})
			continue

		if customer in merge_from_set:
			results.append({"customer": customer, "action": "pending_merge"})
			continue

		has_links = orphan_customers.operational_link_total(counts.get(customer, {})) > 0
		suffix = "_with_links" if has_links else ""

		if dry_run:
			results.append({"customer": customer, "action": "would_disable" + suffix})
			continue

		savepoint = f"disable_customer_{frappe.generate_hash(length=8)}"
		try:
			frappe.db.savepoint(savepoint)
			frappe.db.set_value("Customer", customer, "disabled", 1)
			results.append({"customer": customer, "action": "disabled" + suffix})
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title=f"Customer consolidation: failed to disable {customer}",
				message=frappe.get_traceback(),
			)
			results.append({"customer": customer, "action": "error"})

	return results


def execute_merges(dry_run: bool = False, merges: list[dict] | None = None) -> list[dict]:
	"""Execute every "pending" merge from customer_merges.csv (or the given `merges` rows, for
	testing) with no unresolved field conflicts. Already-applied and invalid rows are skipped.
	Each merge commits independently; a failure rolls back just that one merge and is reported,
	it doesn't stop the rest."""
	customers = gather_customers()
	existing_customers = {c["name"] for c in customers}
	if merges is None:
		merges = decisions.load_customer_merges()
	validated = decisions.validate_customer_merges(merges, existing_customers)

	results = []
	pending_total = sum(1 for row in validated if row["status"] == "pending")
	for row in validated:
		merge_from, merge_into, status = row["merge_from"], row["merge_into"], row["status"]

		if status != "pending":
			results.append(
				{"merge_from": merge_from, "merge_into": merge_into, "status": status, "action": "skipped"}
			)
			continue

		field_types = merge_analysis.get_customer_field_types()
		fieldnames = list(field_types.keys())
		from_values = merge_analysis.get_customer_values(merge_from, fieldnames)
		into_values = merge_analysis.get_customer_values(merge_into, fieldnames)
		diff = merge_analysis.diff_customer_values(from_values, into_values, field_types)
		field_resolutions = decisions.parse_field_resolutions(row.get("field_resolutions", ""))
		unresolved = merge_analysis.find_unresolved_field_conflicts(
			diff["fields_in_conflict"], field_resolutions
		)

		if unresolved:
			results.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"status": "blocked",
					"action": "skipped",
					"unresolved_field_conflicts": unresolved,
				}
			)
			continue

		resolutions = dict(field_resolutions)
		for entry in diff["fields_to_copy"]:
			fieldname = entry.split(":", 1)[0].strip()
			if fieldname == "icorp_client_id":
				# icorp_client_id is UNIQUE at the DB level; copying it here would set it on the
				# survivor via frappe.db.set_value before merge_from is renamed away, so if
				# merge_from still physically holds that value the UNIQUE constraint
				# self-collides. set_customer_icorp_client_ids/apply_customer_record_ids (same
				# module) already backfill icorp_client_id correctly after the merge completes,
				# based on iCorp Client Link ownership, so it never needs auto-copying here.
				continue
			resolutions.setdefault(fieldname, from_values.get(fieldname))

		if dry_run:
			results.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"status": "pending",
					"action": "would_merge",
					"resolutions": resolutions,
				}
			)
			continue

		before_from = _linked_counts(merge_from)
		before_into = _linked_counts(merge_into)

		savepoint = f"merge_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		merge_start = time.monotonic()
		try:
			carried_over = _carry_over_child_tables(merge_from, merge_into)

			skipped_resolutions = []
			for fieldname, value in resolutions.items():
				if fieldname == "disabled":
					# Explicit operator override only (e.g. a reversed-direction merge whose survivor is
					# currently disabled). "disabled" is in merge_analysis._SKIP_FIELDS, so it's never in
					# field_types and never copied or flagged as a conflict -- it's applied only when
					# recorded here.
					frappe.db.set_value("Customer", merge_into, "disabled", value)
					continue
				if fieldname not in field_types:
					skipped_resolutions.append(fieldname)
					continue
				frappe.db.set_value("Customer", merge_into, fieldname, value)

			_rename_doc("Customer", merge_from, merge_into, merge=True, ignore_permissions=True)

			after_into = _linked_counts(merge_into)
			expected = {k: before_from[k] + before_into[k] for k in before_into}
			if after_into != expected:
				raise RuntimeError(
					f"linked-record counts don't reconcile after merge: expected {expected}, got {after_into}"
				)

			frappe.db.commit()
			results.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"status": "pending",
					"action": "merged",
					"resolutions_applied": resolutions,
					"child_rows_carried_over": carried_over,
					"skipped_resolutions": skipped_resolutions,
				}
			)
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title=f"Customer consolidation: merge failed ({merge_from} -> {merge_into})",
				message=frappe.get_traceback(with_context=True),
			)
			results.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"status": "pending",
					"action": "error",
					"error": str(e),
				}
			)
		finally:
			merged_so_far = sum(1 for r in results if r.get("action") in ("merged", "error"))
			print(  # noqa: T201
				f"[consolidation] merge {merged_so_far}/{pending_total}: "
				f"{merge_from} -> {merge_into} ({time.monotonic() - merge_start:.1f}s)",
				flush=True,
			)

	if pending_total:
		print(f"[consolidation] execute_merges: {pending_total} pending merge(s) processed", flush=True)  # noqa: T201

	return results


def _merge_is_satisfied(merge_result: dict) -> bool:
	"""True if a row from execute_merges() means the merge is done: it ran successfully this run
	(action "merged", or "would_merge" in preview), or it was already applied on a prior run
	(status "already_applied", the same classification decisions.validate_customer_merges gives).
	Blocked, invalid, errored, or still-pending rows are not satisfied."""
	if merge_result.get("action") in ("merged", "would_merge"):
		return True
	return merge_result.get("status") == "already_applied"


def rename_customers_from_csv(execute: bool = False, merge_results: list[dict] | None = None) -> list[dict]:
	"""Rename every "approved" Customer in customer_renames.csv to its proposed_name, in file order.
	Non-approved rows (needs_research, etc.) are skipped.

	Dependency gate: a row with depends_on_merge set is only attempted if its current_name is the
	merge_into of a merge that is satisfied per `merge_results` (the return value of execute_merges):
	succeeded this run, or already applied on a prior run. Otherwise it's reported as action
	"blocked" and never attempted. Preview (execute=False) counts merges reported as "would_merge"
	as succeeded, and labels such rows
	"would_rename_pending_merge". A merge already applied on a prior run (status "already_applied")
	also satisfies the gate. Calling with merge_results=None blocks every dependent row that still
	has its current_name.

	execute=False is a read-only preview. Each executed rename commits independently with a
	savepoint; a failure rolls back just that row, is logged, and doesn't stop the rest. After a
	successful DB rename, string references to the old name are repointed to the new name in
	customer_merges.csv (merge_into), icorp_client_assignments.csv (customer),
	customer_distinct_pairs.csv (customer_a/customer_b), and record_reassignments.csv
	(from_customer/to_customer). That CSV rewrite is best-effort and separate: if it fails, the DB rename stands and a warning (csv_warning) is logged
	and returned rather than rolling back the rename.

	Not wired into apply_on_migrate: renames are only ever executed by an explicit run."""
	satisfied_merge_targets = {
		r.get("merge_into") for r in (merge_results or []) if r.get("merge_into") and _merge_is_satisfied(r)
	}

	results = []

	for row in decisions.load_customer_renames():
		current = row["current_name"]
		proposed = (row.get("proposed_name") or "").strip()
		status = (row.get("status") or "").strip()
		depends_on_merge = (row.get("depends_on_merge") or "").strip()
		base = {"current_name": current, "proposed_name": proposed, "status": status}
		if depends_on_merge:
			base["depends_on_merge"] = True

		if status != "approved":
			results.append({**base, "action": "skipped"})
			continue

		if not proposed:
			results.append({**base, "action": "invalid", "error": "proposed_name is empty"})
			continue

		if not frappe.db.exists("Customer", current):
			# Rename already happened on a prior run (or the name is simply gone).
			action = "already_applied" if frappe.db.exists("Customer", proposed) else "missing"
			results.append({**base, "action": action})
			continue

		if depends_on_merge and current not in satisfied_merge_targets:
			results.append(
				{
					**base,
					"action": "blocked",
					"error": "blocked: dependent merge did not succeed",
					"depends_on": current,
				}
			)
			continue

		if proposed != current and frappe.db.exists("Customer", proposed):
			results.append({**base, "action": "invalid", "error": f"'{proposed}' already exists"})
			continue

		if not execute:
			preview_action = "would_rename_pending_merge" if depends_on_merge else "would_rename"
			results.append(
				{
					**base,
					"action": preview_action,
					"csv_rewrites": decisions.rewrite_customer_references(current, proposed, dry_run=True),
				}
			)
			continue

		savepoint = f"rename_customer_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			_rename_doc("Customer", current, proposed, ignore_permissions=True)
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback(save_point=savepoint)
			frappe.log_error(
				title=f"Customer consolidation: rename failed ({current} -> {proposed})",
				message=frappe.get_traceback(with_context=True),
			)
			results.append({**base, "action": "error", "error": str(e)})
			continue

		# DB rename is committed and is the source of truth from here on.
		try:
			csv_rewrites = decisions.rewrite_customer_references(current, proposed)
			results.append({**base, "action": "renamed", "csv_rewrites": csv_rewrites})
		except Exception as e:
			frappe.log_error(
				title=f"Customer consolidation: CSV cross-reference rewrite failed ({current} -> {proposed})",
				message=frappe.get_traceback(with_context=True),
			)
			results.append({**base, "action": "renamed", "csv_rewrites": {}, "csv_warning": str(e)})

	return results


def apply_record_reassignments(
	dry_run: bool = False, rows: list[dict] | None = None, merges: list[dict] | None = None
) -> list[dict]:
	"""Apply every valid row from record_reassignments.csv (or the given `rows`, for testing) —
	moves a single Issue/Warehouse Request/Project to the Customer it's actually about, without
	merging the two Customers. Must run BEFORE execute_merges: a record still under its original
	(soon to be merged-away) Customer name is what `from_customer` is checked against, so running
	this after the merge would make that check fail. Idempotent: already-moved rows are a no-op,
	and a record whose current value is neither from_customer nor to_customer (someone changed it
	since) is left alone and reported."""
	customers = gather_customers()
	existing_customers = {c["name"] for c in customers}

	if merges is None:
		merges = decisions.load_customer_merges()
	merge_map, _cycles = decisions.resolve_merge_map(
		[m for m in decisions.validate_customer_merges(merges, existing_customers) if not m["errors"]]
	)

	if rows is None:
		rows = decisions.load_record_reassignments()
	validated = decisions.validate_record_reassignments(rows, existing_customers, merge_map)

	results = []
	for row in validated:
		doctype = (row.get("doctype") or "").strip()
		name = (row.get("name") or "").strip()
		field = row["resolved_field"]
		from_customer = (row.get("from_customer") or "").strip()
		to_customer = row["resolved_to_customer"]
		errs = row["errors"]

		if errs:
			results.append({"doctype": doctype, "name": name, "status": "invalid", "errors": errs})
			continue

		if not frappe.db.exists(doctype, name):
			results.append({"doctype": doctype, "name": name, "field": field, "action": "missing"})
			continue

		current_value = frappe.db.get_value(doctype, name, field)

		if current_value == to_customer:
			results.append(
				{
					"doctype": doctype,
					"name": name,
					"field": field,
					"customer": to_customer,
					"action": "already_applied",
				}
			)
			continue

		if from_customer and current_value != from_customer:
			results.append(
				{
					"doctype": doctype,
					"name": name,
					"field": field,
					"action": "changed",
					"expected": from_customer,
					"found": current_value,
				}
			)
			continue

		if dry_run:
			results.append(
				{
					"doctype": doctype,
					"name": name,
					"field": field,
					"customer": to_customer,
					"action": "would_reassign",
				}
			)
			continue

		frappe.db.set_value(doctype, name, field, to_customer, update_modified=False)
		results.append(
			{
				"doctype": doctype,
				"name": name,
				"field": field,
				"customer": to_customer,
				"action": "reassigned",
			}
		)

	if not dry_run:
		frappe.db.commit()

	return results


def apply_assignments(
	dry_run: bool = False, assignments: list[dict] | None = None, merges: list[dict] | None = None
) -> list[dict]:
	"""Apply every valid row from icorp_client_assignments.csv (or the given `assignments` rows,
	for testing) — always a deliberate human decision (typed into the CSV directly, or exported
	from the Desk review workflow), so it always overwrites whatever customer was there before."""
	customers = gather_customers()
	existing_customers = {c["name"] for c in customers}
	icorp_client_ids = {
		row["icorp_client_id"] for row in frappe.get_all("iCorp Client Link", fields=["icorp_client_id"])
	}

	if merges is None:
		merges = decisions.load_customer_merges()
	merge_map, _cycles = decisions.resolve_merge_map(
		[m for m in decisions.validate_customer_merges(merges, existing_customers) if not m["errors"]]
	)

	if assignments is None:
		assignments = decisions.load_client_assignments()
	validated = decisions.validate_client_assignments(
		assignments, existing_customers, icorp_client_ids, merge_map
	)

	results = []
	for row in validated:
		client_id, customer, errs = row["client_id"], row["resolved_customer"], row["errors"]

		if errs:
			results.append({"client_id": client_id, "status": "invalid", "errors": errs})
			continue

		if dry_run:
			results.append({"client_id": client_id, "customer": customer, "action": "would_assign"})
			continue

		frappe.db.set_value(
			"iCorp Client Link", client_id, {"customer": customer, "assignment_source": "Manual decision"}
		)
		results.append({"client_id": client_id, "customer": customer, "action": "assigned"})

	if not dry_run:
		frappe.db.commit()

	return results


def set_customer_icorp_client_ids(dry_run: bool = False) -> list[dict]:
	"""For each Customer with a blank icorp_client_id, set it if there's exactly one
	unambiguous top-level client assigned to that Customer (no parent, or a parent belonging to
	a different Customer). Several candidates means the team decides manually; left blank.
	Never overwrites an existing value. If the computed id is already held by a different
	Customer (icorp_client_id is UNIQUE at the database level), the write is skipped and
	reported as a collision rather than attempted, since Customer records that merge or get
	corrected over time can otherwise leave stale holders of an id."""
	customers_without_id = frappe.get_all(
		"Customer", filters={"icorp_client_id": ["in", ["", None]]}, fields=["name"]
	)

	results = []
	for row in customers_without_id:
		customer = row["name"]
		links = frappe.get_all(
			"iCorp Client Link",
			filters={"customer": customer},
			fields=["icorp_client_id", "parent_client"],
		)
		if not links:
			continue

		# "top-level from this customer's perspective": no parent, or the parent isn't one of
		# this same customer's own other clients. A client whose parent IS one of this
		# customer's own clients is a location, not a candidate master.
		own_client_ids = {link["icorp_client_id"] for link in links}
		top_level = [
			link["icorp_client_id"]
			for link in links
			if not link["parent_client"] or link["parent_client"] not in own_client_ids
		]

		if len(top_level) == 1:
			candidate_id = top_level[0]
			held_by = frappe.db.get_value("Customer", {"icorp_client_id": candidate_id}, "name")
			if held_by and held_by != customer:
				results.append(
					{
						"customer": customer,
						"icorp_client_id": candidate_id,
						"action": "collision",
						"held_by": held_by,
					}
				)
				continue
			if not dry_run:
				frappe.db.set_value("Customer", customer, "icorp_client_id", candidate_id)
			results.append({"customer": customer, "icorp_client_id": candidate_id, "action": "set"})
		elif len(top_level) > 1:
			results.append({"customer": customer, "candidates": top_level, "action": "ambiguous"})

	if not dry_run:
		frappe.db.commit()

	return results


def apply_customer_record_ids(dry_run: bool = False) -> list[dict]:
	"""Customer.icorp_client_id is the field provisioning, warehouse requests, and the HubSpot
	deal matcher already rely on — it's the Customer's own iCorp client (its master, or its only
	client). This turns an existing, trusted icorp_client_id value into an actual iCorp Client
	Link assignment, so the two stay in sync without a human re-typing the same decision in the
	review UI. Only acts where the Link's name actually resembles the Customer's name — iCorp ids
	recorded by hand or by provisioning can be wrong (a contractor's client record filed under
	the wrong company, for instance), and a name mismatch is exactly the kind of thing that needs
	a human, not an automatic assignment."""
	customers_with_id = frappe.get_all(
		"Customer",
		filters={"icorp_client_id": ["!=", ""]},
		fields=["name", "customer_name", "icorp_client_id"],
	)

	results = []
	for row in customers_with_id:
		customer, customer_name, client_id = row["name"], row["customer_name"], row["icorp_client_id"]
		link = frappe.db.get_value("iCorp Client Link", client_id, ["client_name", "customer"], as_dict=True)

		if not link:
			results.append({"customer": customer, "icorp_client_id": client_id, "action": "no_link"})
			continue

		if link["customer"]:
			conflict = link["customer"] != customer
			results.append(
				{
					"customer": customer,
					"icorp_client_id": client_id,
					"action": "already_assigned",
					"conflict": conflict,
					"assigned_to": link["customer"],
				}
			)
			continue

		if not _names_resemble(link["client_name"], customer_name):
			results.append(
				{
					"customer": customer,
					"icorp_client_id": client_id,
					"action": "name_mismatch",
					"client_name": link["client_name"],
				}
			)
			continue

		if not dry_run:
			frappe.db.set_value(
				"iCorp Client Link",
				client_id,
				{"customer": customer, "assignment_source": "Customer record"},
			)
		results.append({"customer": customer, "icorp_client_id": client_id, "action": "assigned"})

	if not dry_run:
		frappe.db.commit()

	return results


def _names_resemble(name_a: str | None, name_b: str | None) -> bool:
	"""Pure. True if two names look like the same company: same first normalized word, or at
	least half their normalized words in common (Jaccard). Mirrors the candidate-matching rule
	in _find_name_candidates, but compares two specific names rather than searching an index."""
	words_a = [w for w in normalize_customer_name(name_a).split() if w not in _STOPWORDS]
	words_b = [w for w in normalize_customer_name(name_b).split() if w not in _STOPWORDS]
	if not words_a or not words_b:
		return False

	if words_a[0] == words_b[0]:
		return True

	set_a, set_b = set(words_a), set(words_b)
	union = set_a | set_b
	return bool(union) and len(set_a & set_b) / len(union) >= _JACCARD_MIN


@frappe.whitelist()
def run_apply_decisions(execute: bool = False, sync_first: bool = True) -> dict:
	"""Manual entry point. Defaults to a read-only preview (execute=False): no sync, no writes,
	just a report of what the pending merges/assignments would do against current data."""
	frappe.only_for("System Manager")

	if isinstance(execute, str):
		execute = execute.lower() not in ("0", "false", "")
	if isinstance(sync_first, str):
		sync_first = sync_first.lower() not in ("0", "false", "")

	if not execute:
		merge_preview = execute_merges(dry_run=True)
		return {
			"mode": "preview",
			"customer_creations": create_missing_customers(dry_run=True),
			"record_reassignments": apply_record_reassignments(dry_run=True),
			"merges": merge_preview,
			"customer_renames": rename_customers_from_csv(execute=False, merge_results=merge_preview),
			"customer_record_ids": apply_customer_record_ids(dry_run=True),
			"assignments": apply_assignments(dry_run=True),
			"customer_icorp_client_ids": set_customer_icorp_client_ids(dry_run=True),
		}

	sync_result = sync_icorp_client_links() if sync_first else None
	customer_creation_results = create_missing_customers(dry_run=False)
	record_reassignment_results = apply_record_reassignments(dry_run=False)
	merge_results = execute_merges(dry_run=False)
	customer_record_id_results = apply_customer_record_ids(dry_run=False)
	assignment_results = apply_assignments(dry_run=False)
	customer_icorp_client_id_results = set_customer_icorp_client_ids(dry_run=False)
	# Renames run after merges (so depends_on_merge rows target the survivor) and after assignments
	# (which still reference pre-rename names in icorp_client_assignments.csv).
	rename_results = rename_customers_from_csv(execute=True, merge_results=merge_results)
	refresh_match_proposals()

	return {
		"mode": "executed",
		"sync": sync_result,
		"customer_creations": customer_creation_results,
		"record_reassignments": record_reassignment_results,
		"merges": merge_results,
		"customer_record_ids": customer_record_id_results,
		"assignments": assignment_results,
		"customer_icorp_client_ids": customer_icorp_client_id_results,
		"customer_renames": rename_results,
	}


def _decisions_file_hash() -> str:
	hasher = hashlib.sha256()
	for path in (
		decisions.CUSTOMER_MERGES_PATH,
		decisions.CLIENT_ASSIGNMENTS_PATH,
		decisions.CUSTOMER_DISTINCT_PAIRS_PATH,
		decisions.CUSTOMERS_TO_CREATE_PATH,
		decisions.RECORD_REASSIGNMENTS_PATH,
		decisions.CUSTOMER_RENAMES_PATH,
	):
		with open(path, "rb") as f:
			hasher.update(f.read())
	return hasher.hexdigest()


def apply_on_migrate() -> None:
	"""Hooked via `after_migrate`. Skips entirely if the decision files (including
	customer_renames.csv) are unchanged since the last successful run. Syncs from iCorp FIRST so a
	first-ever deploy's iCorp Client Link table is populated before assignments are validated
	against it — otherwise every assignment row would fail "client does not exist" and silently
	never retry. Renames run right after merges (so a depends_on_merge rename sees this run's merge
	results) and only for "approved" rows.

	Fails the migrate (does not swallow the error) on any exception, any blocked/errored merge,
	any failed/blocked rename, or any invalid assignment/record-reassignment/customer-creation —
	so a partial or bad apply shows up as a failed deploy instead of a silent retry-forever state.
	The hash is only saved once everything that could be applied actually was; a genuinely clean
	run (nothing left to retry) is required before `drop_legacy_customer_icorp_client_id` (the next
	after_migrate hook) is allowed to drop the legacy column.

	Prints per-phase elapsed time to migrate output, since a long apply run is the main risk for
	a deploy with a hard job timeout — this is the only way to tell, from a timed-out migrate's
	job log, how far it got and which phase to speed up.
	"""
	if not _icorp_is_configured():
		print(  # noqa: T201
			"[consolidation] Skipping: iCorp API credentials are not configured on this site.",
			flush=True,
		)
		return

	current_hash = _decisions_file_hash()
	last_applied_hash = frappe.db.get_default(_APPLIED_HASH_KEY)

	if current_hash == last_applied_hash:
		return

	overall_start = time.monotonic()
	failure_summary = None

	def _log_phase(label, start):
		print(f"[consolidation] {label}: {time.monotonic() - start:.1f}s", flush=True)  # noqa: T201

	try:
		t0 = time.monotonic()
		sync_icorp_client_links()
		_log_phase("sync_icorp_client_links", t0)

		t0 = time.monotonic()
		customer_creation_results = create_missing_customers(dry_run=False)
		_log_phase("create_missing_customers", t0)

		t0 = time.monotonic()
		record_reassignment_results = apply_record_reassignments(dry_run=False)
		_log_phase("apply_record_reassignments", t0)

		t0 = time.monotonic()
		merge_results = execute_merges(dry_run=False)
		_log_phase("execute_merges", t0)

		t0 = time.monotonic()
		rename_results = rename_customers_from_csv(execute=True, merge_results=merge_results)
		_log_phase("rename_customers_from_csv", t0)

		t0 = time.monotonic()
		customer_record_id_results = apply_customer_record_ids(dry_run=False)
		_log_phase("apply_customer_record_ids", t0)

		t0 = time.monotonic()
		assignment_results = apply_assignments(dry_run=False)
		_log_phase("apply_assignments", t0)

		t0 = time.monotonic()
		customer_icorp_client_id_results = set_customer_icorp_client_ids(dry_run=False)
		_log_phase("set_customer_icorp_client_ids", t0)

		t0 = time.monotonic()
		run_backfill()
		_log_phase("run_backfill", t0)

		t0 = time.monotonic()
		refresh_match_proposals()
		_log_phase("refresh_match_proposals", t0)

		print(f"[consolidation] TOTAL: {time.monotonic() - overall_start:.1f}s", flush=True)  # noqa: T201

		# Routine action=="skipped" + status in ("already_applied", "invalid") merges are expected
		# steady-state on every run after a merge has succeeded once (merge_from is already gone,
		# nothing to retry) -- only action=="error" (exception during execution) or status=="blocked"
		# (unresolved field conflict) are genuine failures worth withholding the hash / retrying for.
		skipped_merges = [
			r for r in merge_results if r.get("action") == "error" or r.get("status") == "blocked"
		]
		skipped_renames = [r for r in rename_results if r.get("action") in ("error", "blocked")]
		invalid_assignments = [r for r in assignment_results if r.get("status") == "invalid"]
		# Rows whose ONLY problem is "this iCorp client isn't in this environment's iCorp Client Link
		# table yet" are expected, environment-dependent, and not retriable by anything this function
		# does differently next time except simply running sync_icorp_client_links() again on the next
		# migrate -- so they're reported (still visible in the Error Log below) but must NOT fail
		# the migrate or block the applied-hash from being saved, unlike every other kind of invalid
		# assignment row.
		pending_sync_assignments = [
			r for r in invalid_assignments if decisions.is_pending_sync_only(r.get("errors", []))
		]
		hard_invalid_assignments = [r for r in invalid_assignments if r not in pending_sync_assignments]
		invalid_record_reassignments = [
			r for r in record_reassignment_results if r.get("status") == "invalid"
		]
		skipped_customer_record_ids = [
			r
			for r in customer_record_id_results
			if r.get("action") == "name_mismatch"
			or (r.get("action") == "already_assigned" and r.get("conflict"))
		]
		problem_customer_icorp_client_ids = [
			r for r in customer_icorp_client_id_results if r.get("action") in ("ambiguous", "collision")
		]
		invalid_customer_creations = [
			r for r in customer_creation_results if r.get("action") in ("invalid", "name_mismatch")
		]

		if (
			skipped_merges
			or skipped_renames
			or hard_invalid_assignments
			or invalid_record_reassignments
			or skipped_customer_record_ids
			or problem_customer_icorp_client_ids
			or invalid_customer_creations
			or pending_sync_assignments
		):
			frappe.log_error(
				title="Customer consolidation: some decisions skipped on apply_on_migrate",
				message=frappe.as_json(
					{
						"skipped_merges": skipped_merges,
						"skipped_renames": skipped_renames,
						"hard_invalid_assignments": hard_invalid_assignments,
						"pending_sync_assignments": pending_sync_assignments,
						"invalid_record_reassignments": invalid_record_reassignments,
						"skipped_customer_record_ids": skipped_customer_record_ids,
						"problem_customer_icorp_client_ids": problem_customer_icorp_client_ids,
						"invalid_customer_creations": invalid_customer_creations,
					}
				),
			)

		if (
			skipped_merges
			or skipped_renames
			or hard_invalid_assignments
			or invalid_record_reassignments
			or invalid_customer_creations
		):
			# A blocked merge, a failed or blocked rename, or a genuinely invalid assignment row
			# (anything other than "this iCorp client isn't synced to this environment yet") means
			# this CSV content hasn't been fully applied yet. Commit whatever DID apply cleanly, but
			# don't save the hash -- and fail the migrate so this shows up as a failed deploy
			# instead of a silent retry-forever state. skipped_customer_record_ids,
			# problem_customer_icorp_client_ids, and pending_sync_assignments are not retried on /
			# do not fail the migrate: the first two are informational (a human decides the right
			# value; a repeat migrate run can't resolve them on its own the way a field_resolutions
			# edit or a cleared icorp_client_id collision would), and pending_sync_assignments is an
			# environment-dependent condition this run can't fix any differently next time either
			# (it may never resolve here, e.g. dev.local syncing from a different iCorp than the
			# CSV's source data) -- none of these three trigger failure_summary / the throw below.
			frappe.db.commit()
			failure_summary = (
				f"{len(skipped_merges)} merge(s), {len(skipped_renames)} rename(s), "
				f"{len(hard_invalid_assignments)} assignment(s), "
				f"{len(invalid_record_reassignments)} record reassignment(s), "
				f"{len(invalid_customer_creations)} customer creation(s) could not be applied."
			)
		else:
			frappe.db.set_default(_APPLIED_HASH_KEY, current_hash)
			frappe.db.commit()
	except Exception:
		frappe.log_error(
			title="Customer consolidation: apply_on_migrate failed",
			message=frappe.get_traceback(with_context=True),
		)
		raise

	if failure_summary:
		frappe.throw(
			f"Customer consolidation did not fully apply: {failure_summary} See the Error Log for details."
		)


_DISABLE_APPLIED_HASH_KEY = "customer_consolidation_disable_hash"


def _disable_file_hash() -> str:
	with open(decisions.CUSTOMERS_TO_DISABLE_PATH, "rb") as f:
		return hashlib.sha256(f.read()).hexdigest()


def apply_customer_disables_on_migrate() -> None:
	"""Hooked via `after_migrate`, independently of apply_on_migrate's hash gate. Skips entirely
	if customers_to_disable.csv is unchanged since the last successful run. Does not save the hash
	if any row errored, so the next migrate retries automatically.
	8
	pending_merge is not treated as a problem — it's expected steady-state for customers queued
	for deletion that are also pending a merge (the merge takes precedence)."""
	current_hash = _disable_file_hash()
	last_applied_hash = frappe.db.get_default(_DISABLE_APPLIED_HASH_KEY)

	if current_hash == last_applied_hash:
		return

	try:
		results = disable_decided_customers(dry_run=False)

		problems = [r for r in results if r["action"] == "error"]
		if problems:
			frappe.log_error(
				title="Customer consolidation: some deletions skipped on apply_customer_disables_on_migrate",
				message=frappe.as_json({"problems": problems}),
			)
			frappe.db.commit()
			return

		frappe.db.set_default(_DISABLE_APPLIED_HASH_KEY, current_hash)
		frappe.db.commit()
	except Exception:
		frappe.log_error(
			title="Customer consolidation: apply_customer_disables_on_migrate failed",
			message=frappe.get_traceback(),
		)


_LEGACY_ICORP_CLIENT_ID_DROP_FLAG = "customer_icorp_client_id_column_dropped"


def drop_legacy_customer_icorp_client_id() -> None:
	"""Hooked via `after_migrate`, registered immediately after `apply_on_migrate` in
	hooks.py's after_migrate list. Drops the legacy Customer.icorp_client_id column,
	but only once the consolidation has actually succeeded for the CSV content
	currently on disk -- i.e. only when apply_on_migrate's own hash check would
	consider this run "nothing left to do" (current_hash == last_applied_hash).
	Since apply_on_migrate always runs first within the same migrate (and now fails
	the migrate outright on any unresolved row, rather than silently leaving the
	hash unsaved), this function is only ever reached at all when apply_on_migrate's
	own run this migrate succeeded (or had nothing to do) -- it never has to guess.

	Writes a CSV report of any Customer whose legacy value doesn't match an iCorp
	Client Link currently assigned to that same Customer, before dropping the
	column, so nothing is silently lost. Idempotent: records a Default Value flag
	once done, so this is a fast no-op on every later migrate.
	"""
	if frappe.db.get_default(_LEGACY_ICORP_CLIENT_ID_DROP_FLAG):
		return

	if not frappe.db.has_column("Customer", "icorp_client_id"):
		frappe.db.set_default(_LEGACY_ICORP_CLIENT_ID_DROP_FLAG, "1")
		frappe.db.commit()
		return

	current_hash = _decisions_file_hash()
	last_applied_hash = frappe.db.get_default(_APPLIED_HASH_KEY)
	if current_hash != last_applied_hash:
		# The consolidation hasn't (yet) succeeded for the CSVs currently on disk this
		# run -- leave the column in place; apply_on_migrate will retry next migrate.
		return

	import csv
	import os

	rows = frappe.db.sql(
		"""
		select c.name as customer, c.icorp_client_id, l.customer as link_customer
		from tabCustomer c
		left join `tabiCorp Client Link` l on l.name = c.icorp_client_id
		where ifnull(c.icorp_client_id, '') != ''
		""",
		as_dict=True,
	)
	mismatched = [r for r in rows if r.link_customer != r.customer]

	if mismatched:
		site_path = frappe.get_site_path("private", "files")
		os.makedirs(site_path, exist_ok=True)
		path = os.path.join(
			site_path, f"legacy_customer_icorp_client_id_mismatches_{frappe.utils.nowdate()}.csv"
		)
		with open(path, "w", newline="") as f:
			writer = csv.DictWriter(f, fieldnames=["customer", "icorp_client_id", "link_customer"])
			writer.writeheader()
			writer.writerows(mismatched)
		frappe.logger("deployments").info(
			f"Legacy Customer.icorp_client_id mismatches before column drop: {path} ({len(mismatched)} rows)"
		)

	if frappe.db.exists("Custom Field", "Customer-icorp_client_id"):
		frappe.delete_doc("Custom Field", "Customer-icorp_client_id", ignore_permissions=True)

	frappe.db.sql_ddl("ALTER TABLE `tabCustomer` DROP COLUMN `icorp_client_id`")

	frappe.db.set_default(_LEGACY_ICORP_CLIENT_ID_DROP_FLAG, "1")
	frappe.db.commit()
