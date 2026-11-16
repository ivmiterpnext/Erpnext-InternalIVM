"""Operator entry point for the Customer-consolidation apply run.

Runs every phase in a fixed canonical order, reusing the existing apply/decisions/backfill
functions unchanged. Each phase has a preview mode (dry run) and an execute mode.

Usage (from the bench directory):
	bench --site <site> execute ivm.customer_consolidation.run.run_consolidation
	bench --site <site> execute "ivm.customer_consolidation.run.run_consolidation" --kwargs "{'execute': True}"

Dry run (execute=False) never writes: sync and backfill have no preview mode and are reported
as "no preview available" rather than run.

Neither mode raises on problem rows. After ALL selected phases have run, a final line
"[consolidation] RESULT: ..." is printed (CLEAN, COMPLETED WITH n PROBLEM ROW(S), or DRY RUN with
n flagged). The returned dict carries "result" ("clean" | "problems") and "problem_rows" (n).
A bad row never stops later phases; per-row commits mean a re-run resumes from whatever is still
pending. Raising under `bench execute` made frappe fall back to eval'ing the method path, which
produced a misleading NameError instead of the real outcome.
"""

import time

import frappe

from ivm.customer_consolidation.apply import (
	_icorp_is_configured,
	apply_assignments,
	apply_customer_record_ids,
	apply_record_reassignments,
	create_missing_customers,
	disable_decided_customers,
	execute_merges,
	rename_customers_from_csv,
	set_customer_icorp_client_ids,
	sync_icorp_client_links,
)
from ivm.deployments.patches.backfill_project_icorp_client import run_backfill

# Statuses that count as a failure for the execute-mode raise.
PROBLEM_STATUSES = ("invalid", "blocked", "error")

# Every status a row can carry. "applied" (executed success) and "skipped" (informational,
# not-a-failure, e.g. an ambiguous set_icorp_ids row left blank on purpose) are added beyond
# the six preview statuses requested.
STATUS_KEYS = (
	"pending",
	"already_applied",
	"invalid",
	"blocked",
	"skipped_live",
	"error",
	"applied",
	"skipped",
)


def _row(status: str, label: str, reason: str = "") -> dict:
	return {"status": status, "label": label, "reason": reason}


def _ok(execute: bool) -> str:
	"""Status for a row that would be (dry run) or was (execute) successfully applied."""
	return "applied" if execute else "pending"


def _unexpected(label: str, action) -> dict:
	return _row("error", label, f"unexpected action {action!r}")


# --- phase runners ---------------------------------------------------------------------------
# Each runner takes `execute` and returns (rows, note). `rows` is None when the phase has no
# preview mode in dry run. Runners only call the existing functions; they add no write logic.


def _run_sync(execute: bool):
	if not execute:
		return None, "no preview available"
	result = sync_icorp_client_links()
	if result is None:
		return [], "skipped: iCorp API credentials not configured"
	return [], f"total={result['total']} created={result['created']} updated={result['updated']}"


def _run_create(execute: bool):
	rows = []
	for r in create_missing_customers(dry_run=not execute):
		name, action = r["customer_name"], r["action"]
		if action == "exists":
			rows.append(_row("already_applied", name))
		elif action in ("would_create", "created"):
			rows.append(_row(_ok(execute), name))
		elif action == "invalid":
			rows.append(_row("invalid", name, r.get("reason", "")))
		elif action == "name_mismatch":
			rows.append(_row("invalid", name, f"created as '{r.get('created_as')}'"))
		else:
			rows.append(_unexpected(name, action))
	return rows, ""


def _run_rename(execute: bool):
	rows = []
	for r in rename_customers_from_csv(execute=execute):
		label = f"{r['current_name']} -> {r['proposed_name']}"
		action = r["action"]
		if action == "skipped":
			rows.append(_row("skipped", label, f"status '{r.get('status')}' (not approved)"))
		elif action == "invalid":
			rows.append(_row("invalid", label, r.get("reason", "")))
		elif action == "already_applied":
			rows.append(_row("already_applied", label))
		elif action in ("would_rename", "renamed"):
			rows.append(_row(_ok(execute), label))
		elif action == "error":
			rows.append(_row("error", label, r.get("error", "")))
		else:
			rows.append(_unexpected(label, action))
	return rows, ""


def _run_reassign(execute: bool):
	rows = []
	for r in apply_record_reassignments(dry_run=not execute):
		label = f"{r.get('doctype')} {r.get('name')}" + (
			f".{r['field']} -> {r['customer']}" if r.get("field") else ""
		)
		action = r.get("action")
		if r.get("status") == "invalid":
			rows.append(_row("invalid", label, r.get("reason", "")))
		elif action == "missing":
			rows.append(_row("invalid", label, "record not found"))
		elif action == "already_applied":
			rows.append(_row("already_applied", label))
		elif action == "changed":
			rows.append(_row("blocked", label, f"expected '{r.get('expected')}', found '{r.get('found')}'"))
		elif action in ("would_reassign", "reassigned"):
			rows.append(_row(_ok(execute), label))
		else:
			rows.append(_unexpected(label, action))
	return rows, ""


def _run_merge(execute: bool):
	rows = []
	for r in execute_merges(dry_run=not execute):
		label = f"{r['merge_from']} -> {r['merge_into']}"
		action, status = r.get("action"), r.get("status")
		if action == "error":
			rows.append(_row("error", label, r.get("error", "")))
		elif status == "blocked":
			conflicts = ", ".join(str(c) for c in r.get("unresolved_field_conflicts", []))
			rows.append(_row("blocked", label, f"unresolved field conflicts: {conflicts}"))
		elif status == "invalid":
			rows.append(_row("invalid", label, r.get("reason", "")))
		elif status == "already_applied":
			rows.append(_row("already_applied", label))
		elif action in ("would_merge", "merged"):
			rows.append(_row(_ok(execute), label))
		else:
			rows.append(_unexpected(label, action))
	return rows, ""


def _run_assign(execute: bool):
	rows = []
	for r in apply_assignments(dry_run=not execute):
		label = f"iCorp {r.get('client_id')}" + (f" -> {r['customer']}" if r.get("customer") else "")
		action = r.get("action")
		if r.get("status") == "invalid":
			rows.append(_row("invalid", label, r.get("reason", "")))
		elif action == "skipped_live":
			rows.append(_row("skipped_live", label, "Customer-form assignment is live; not overwritten"))
		elif action == "already_applied":
			rows.append(_row("already_applied", label))
		elif action in ("would_assign", "assigned"):
			rows.append(_row(_ok(execute), label))
		else:
			rows.append(_unexpected(label, action))
	return rows, ""


def _run_record_ids(execute: bool):
	rows = []
	for r in apply_customer_record_ids(dry_run=not execute):
		label = f"{r.get('customer')} (iCorp {r.get('icorp_client_id')})"
		action = r.get("action")
		if action == "assigned":
			rows.append(_row(_ok(execute), label))
		elif action == "already_assigned":
			if r.get("conflict"):
				rows.append(
					_row("blocked", label, f"iCorp client already assigned to '{r.get('assigned_to')}'")
				)
			else:
				rows.append(_row("already_applied", label))
		elif action == "name_mismatch":
			# Known intentional decline (e.g. Kijero, LLC. / US Navy): informational, not a problem row.
			rows.append(
				_row(
					"skipped", label, f"iCorp client name '{r.get('client_name')}' doesn't resemble Customer"
				)
			)
		elif action == "no_link":
			rows.append(_row("invalid", label, "iCorp Client Link does not exist"))
		else:
			rows.append(_unexpected(label, action))
	return rows, ""


def _run_set_ids(execute: bool):
	rows = []
	for r in set_customer_icorp_client_ids(dry_run=not execute):
		customer = r.get("customer")
		action = r.get("action")
		if action == "set":
			rows.append(_row(_ok(execute), f"{customer} -> iCorp {r.get('icorp_client_id')}"))
		elif action == "collision":
			rows.append(
				_row(
					"blocked",
					f"{customer} -> iCorp {r.get('icorp_client_id')}",
					f"icorp_client_id already held by '{r.get('held_by')}'",
				)
			)
		elif action == "ambiguous":
			rows.append(
				_row(
					"skipped",
					customer,
					f"{len(r.get('candidates', []))} candidate clients; left blank for manual decision",
				)
			)
		else:
			rows.append(_unexpected(customer, action))
	return rows, ""


def _run_disable(execute: bool):
	results = disable_decided_customers(dry_run=not execute)
	if execute:
		# disable_decided_customers does not commit; commit here so each run's disables persist.
		frappe.db.commit()
	rows = []
	for r in results:
		customer, action = r["customer"], r["action"]
		if action in ("would_disable", "would_disable_with_links", "disabled", "disabled_with_links"):
			rows.append(_row(_ok(execute), customer, "has operational links" if "links" in action else ""))
		elif action in ("already_gone", "already_disabled"):
			rows.append(_row("already_applied", customer))
		elif action == "pending_merge":
			rows.append(_row("blocked", customer, "pending merge in customer_merges.csv (merge first)"))
		elif action == "error":
			rows.append(_row("error", customer, "disable failed; see Error Log"))
		else:
			rows.append(_unexpected(customer, action))
	return rows, ""


def _run_backfill(execute: bool):
	if not execute:
		return None, "no preview available"
	run_backfill()
	# run_backfill does not commit; commit here so its writes persist.
	frappe.db.commit()
	return [], "run_backfill completed (report CSV written to private/files; not returned)"


PHASES = [
	("sync", _run_sync),
	("create", _run_create),
	("rename", _run_rename),
	("reassign", _run_reassign),
	("merge", _run_merge),
	("assign", _run_assign),
	("record_ids", _run_record_ids),
	("set_icorp_ids", _run_set_ids),
	("disable", _run_disable),
	("backfill", _run_backfill),
]
PHASE_KEYS = [key for key, _ in PHASES]


def _count(rows: list[dict]) -> dict[str, int]:
	counts = {key: 0 for key in STATUS_KEYS}
	for r in rows:
		counts[r["status"]] = counts.get(r["status"], 0) + 1
	return counts


_ALWAYS_SHOWN_STATUSES = ("pending", "already_applied", "invalid", "blocked", "skipped_live", "error")


def _format_counts(counts: dict[str, int]) -> str:
	"""The six requested statuses always print; applied/skipped print only when non-zero."""
	shown = [k for k in STATUS_KEYS if k in _ALWAYS_SHOWN_STATUSES or counts.get(k)]
	return ", ".join(f"{k}={counts.get(k, 0)}" for k in shown)


def _log(msg: str) -> None:
	print(f"[consolidation] {msg}", flush=True)  # noqa: T201


def run_consolidation(execute: bool = False, phases: list[str] | None = None) -> dict:
	"""Run the consolidation phases in canonical order. See module docstring.

	execute=False: dry run, each phase in preview mode, no writes.
	execute=True: apply every selected phase. Never raises for problem rows; see the final RESULT line.
	phases: optional subset of PHASE_KEYS; always run in canonical order regardless of list order.

	Returns a dict keyed by phase: {mode, elapsed_seconds, status_counts, rows, note}, plus two
	top-level keys: "result" ("clean" | "problems") and "problem_rows" (int).
	The iCorp-not-configured early return is {} (nothing ran).
	"""
	if not _icorp_is_configured():
		_log("Skipping: iCorp API credentials are not configured on this site. Nothing was run.")
		return {}

	if phases is None:
		selected = list(PHASES)
	else:
		unknown = [p for p in phases if p not in PHASE_KEYS]
		if unknown:
			raise ValueError(f"Unknown phase(s) {unknown}; valid keys are {PHASE_KEYS}")
		wanted = set(phases)
		selected = [(key, runner) for key, runner in PHASES if key in wanted]

	mode = "EXECUTE" if execute else "DRY RUN"
	_log(f"=== run_consolidation {mode}: phases {[key for key, _ in selected]} ===")

	results: dict[str, dict] = {}
	total_problems = 0

	for key, runner in selected:
		_log(f"--- phase {key} ---")
		t0 = time.monotonic()
		try:
			rows, note = runner(execute)
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(
				title=f"Customer consolidation run: phase {key} failed",
				message=frappe.get_traceback(with_context=True),
			)
			rows, note = [_row("error", f"phase {key}", str(e))], "phase raised; see Error Log"
		elapsed = time.monotonic() - t0

		if rows is None:
			_log(f"{key}: no preview available ({elapsed:.1f}s)")
			results[key] = {
				"mode": "no_preview",
				"elapsed_seconds": round(elapsed, 2),
				"status_counts": {},
				"rows": [],
				"note": note,
			}
			continue

		counts = _count(rows)
		problems = [r for r in rows if r["status"] in PROBLEM_STATUSES]
		total_problems += len(problems)

		_log(f"{key}: {_format_counts(counts)} ({elapsed:.1f}s){' -- ' + note if note else ''}")
		for r in problems:
			_log(f"  [{r['status']}] {r['label']}: {r['reason']}")
		# skipped rows are informational (not problems) but still listed with their reason.
		for r in rows:
			if r["status"] == "skipped" and r["reason"]:
				_log(f"  [skipped] {r['label']}: {r['reason']}")

		results[key] = {
			"mode": "executed" if execute else "preview",
			"elapsed_seconds": round(elapsed, 2),
			"status_counts": counts,
			"rows": rows,
			"note": note,
		}

	_log("=== summary ===")
	for key, result in results.items():
		counts = result["status_counts"]
		if result["mode"] == "no_preview":
			_log(f"{key}: no preview available ({result['elapsed_seconds']}s)")
		else:
			_log(f"{key}: {_format_counts(counts)} ({result['elapsed_seconds']}s)")
	_log(f"problem rows (invalid/blocked/error): {total_problems}")

	if total_problems == 0:
		_log("RESULT: CLEAN (no problem rows)")
	elif execute:
		_log(
			f"RESULT: COMPLETED WITH {total_problems} PROBLEM ROW(S) — review the "
			"[invalid]/[blocked]/[error] lines above and the Error Log"
		)
	else:
		_log(f"RESULT: DRY RUN — {total_problems} problem row(s) flagged")

	results["result"] = "problems" if total_problems else "clean"
	results["problem_rows"] = total_problems
	return results
