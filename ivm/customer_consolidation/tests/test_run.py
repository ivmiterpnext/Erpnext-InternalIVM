"""Tests for ivm.customer_consolidation.run.run_consolidation.

Every phase function is mocked, so these tests never write Customer/iCorp data. They cover
the gating (iCorp not configured), phase selection/order, dry-run behavior, and the
problem-row reporting: run_consolidation never raises; it returns result/problem_rows and
prints a final RESULT line.
"""

from unittest import mock

from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation import run

_PHASE_TARGETS = {
	"sync": "sync_icorp_client_links",
	"create": "create_missing_customers",
	"rename": "rename_customers_from_csv",
	"reassign": "apply_record_reassignments",
	"merge": "execute_merges",
	"assign": "apply_assignments",
	"record_ids": "apply_customer_record_ids",
	"set_icorp_ids": "set_customer_icorp_client_ids",
	"disable": "disable_decided_customers",
	"backfill": "run_backfill",
}

_DEFAULT_RETURNS = {
	"sync": {"total": 0, "created": 0, "updated": 0},
	"create": [],
	"rename": [],
	"reassign": [],
	"merge": [],
	"assign": [],
	"record_ids": [],
	"set_icorp_ids": [],
	"disable": [],
	"backfill": None,
}


class _Harness:
	"""Patches every phase function plus the iCorp gate. `order` records call sequence."""

	def __init__(self, configured: bool = True):
		self.order: list[str] = []
		self.mocks: dict[str, mock.MagicMock] = {}
		self.commit = mock.MagicMock(name="frappe.db.commit")
		self._patches = [
			mock.patch.object(run, "_icorp_is_configured", return_value=configured),
			mock.patch.object(run.frappe.db, "commit", self.commit),
		]
		for key, target in _PHASE_TARGETS.items():
			default = _DEFAULT_RETURNS[key]
			m = mock.MagicMock(name=target, side_effect=self._recorder(key, default))
			self.mocks[key] = m
			self._patches.append(mock.patch.object(run, target, m))

	def _recorder(self, key, default):
		def _side_effect(*args, **kwargs):
			self.order.append(key)
			return default.copy() if isinstance(default, list) else default

		return _side_effect

	def set_return(self, key: str, value) -> None:
		"""Override one phase's return value (keeps call recording intact)."""
		default = value
		self.mocks[key].side_effect = self._recorder_with(key, default)

	def _recorder_with(self, key, value):
		def _side_effect(*args, **kwargs):
			self.order.append(key)
			return value

		return _side_effect

	def __enter__(self):
		for p in self._patches:
			p.start()
		return self

	def __exit__(self, *exc):
		for p in reversed(self._patches):
			p.stop()
		return False


class TestRunConsolidation(ERPNextTestSuite):
	"""run_consolidation: gating, selection, dry run, execute failure rule."""

	def test_refuses_when_icorp_not_configured(self):
		with _Harness(configured=False) as h:
			result = run.run_consolidation(execute=True)

		self.assertEqual(result, {})
		self.assertEqual(h.order, [])
		for key, m in h.mocks.items():
			self.assertFalse(m.called, f"{key} must not run when iCorp is not configured")

	def test_phase_subset_runs_in_canonical_order(self):
		# Execute mode: sync has no dry-run mode, so it only runs (and gets recorded) when executing.
		with _Harness() as h:
			run.run_consolidation(execute=True, phases=["disable", "sync", "merge"])

		self.assertEqual(h.order, ["sync", "merge", "disable"])

	def test_unknown_phase_key_raises_before_running_anything(self):
		with _Harness() as h:
			with self.assertRaises(ValueError):
				run.run_consolidation(execute=False, phases=["merge", "not_a_phase"])

		self.assertEqual(h.order, [])

	def test_phase_keys_are_in_spec_order(self):
		self.assertEqual(
			run.PHASE_KEYS,
			[
				"sync",
				"create",
				"rename",
				"reassign",
				"merge",
				"assign",
				"record_ids",
				"set_icorp_ids",
				"disable",
				"backfill",
			],
		)

	def test_dry_run_calls_previews_and_never_writes(self):
		with _Harness() as h:
			result = run.run_consolidation(execute=False)

		# Preview modes were requested.
		h.mocks["create"].assert_called_once_with(dry_run=True)
		h.mocks["rename"].assert_called_once_with(execute=False)
		h.mocks["reassign"].assert_called_once_with(dry_run=True)
		h.mocks["merge"].assert_called_once_with(dry_run=True)
		h.mocks["assign"].assert_called_once_with(dry_run=True)
		h.mocks["record_ids"].assert_called_once_with(dry_run=True)
		h.mocks["set_icorp_ids"].assert_called_once_with(dry_run=True)
		h.mocks["disable"].assert_called_once_with(dry_run=True)

		# No preview mode for sync/backfill: they must not run at all, and nothing commits.
		h.mocks["sync"].assert_not_called()
		h.mocks["backfill"].assert_not_called()
		h.commit.assert_not_called()

		self.assertEqual(result["sync"]["mode"], "no_preview")
		self.assertEqual(result["backfill"]["mode"], "no_preview")
		self.assertEqual(result["merge"]["mode"], "preview")

	def test_execute_with_invalid_row_does_not_raise_and_reports_problems(self):
		with _Harness() as h:
			h.set_return(
				"create",
				[
					{
						"customer_name": "Bad Co",
						"action": "invalid",
						"reason": "Customer Group is a Group node",
					}
				],
			)
			result = run.run_consolidation(execute=True)

		self.assertEqual(result["result"], "problems")
		self.assertEqual(result["problem_rows"], 1)
		self.assertEqual(result["create"]["status_counts"]["invalid"], 1)

		# Later phases still ran after the invalid row in `create`.
		for key in (
			"rename",
			"reassign",
			"merge",
			"assign",
			"record_ids",
			"set_icorp_ids",
			"disable",
			"backfill",
		):
			self.assertTrue(h.mocks[key].called, f"{key} should still run after an invalid row in create")
		self.assertEqual(h.order[-1], "backfill")

	def test_execute_with_blocked_merge_does_not_raise_and_reports_problems(self):
		with _Harness() as h:
			h.set_return(
				"merge",
				[
					{
						"merge_from": "A",
						"merge_into": "B",
						"status": "blocked",
						"action": "skipped",
						"unresolved_field_conflicts": ["tax_id"],
					}
				],
			)
			result = run.run_consolidation(execute=True)

		self.assertEqual(result["result"], "problems")
		self.assertEqual(result["problem_rows"], 1)
		self.assertTrue(h.mocks["assign"].called)
		self.assertTrue(h.mocks["backfill"].called)

	def test_execute_clean_reports_clean(self):
		with _Harness() as h:
			result = run.run_consolidation(execute=True)

		self.assertEqual(h.order[-1], "backfill")
		self.assertEqual(result["create"]["mode"], "executed")
		self.assertEqual(result["sync"]["mode"], "executed")
		self.assertEqual(result["result"], "clean")
		self.assertEqual(result["problem_rows"], 0)

	def test_dry_run_with_invalid_rows_does_not_raise(self):
		with _Harness() as h:
			h.set_return(
				"assign",
				[{"client_id": "123", "status": "invalid", "reason": "customer is empty", "errors": []}],
			)
			result = run.run_consolidation(execute=False)

		self.assertEqual(result["assign"]["status_counts"]["invalid"], 1)
		self.assertEqual(result["result"], "problems")
		self.assertEqual(result["problem_rows"], 1)

	def test_phase_exception_is_recorded_as_error_and_later_phases_still_run(self):
		with _Harness() as h:
			h.mocks["reassign"].side_effect = RuntimeError("boom")
			result = run.run_consolidation(execute=True)

		self.assertTrue(h.mocks["merge"].called)
		self.assertTrue(h.mocks["backfill"].called)
		self.assertEqual(result["reassign"]["status_counts"]["error"], 1)
		self.assertEqual(result["result"], "problems")
		self.assertEqual(result["problem_rows"], 1)

	def test_final_result_line(self):
		cases = [
			(True, None, "RESULT: CLEAN (no problem rows)"),
			(
				True,
				[{"customer_name": "Bad Co", "action": "invalid", "reason": "x"}],
				"RESULT: COMPLETED WITH 1 PROBLEM ROW(S) — review the "
				"[invalid]/[blocked]/[error] lines above and the Error Log",
			),
			(
				False,
				[{"customer_name": "Bad Co", "action": "invalid", "reason": "x"}],
				"RESULT: DRY RUN — 1 problem row(s) flagged",
			),
		]
		for execute, create_rows, expected in cases:
			with self.subTest(execute=execute, expected=expected):
				with _Harness() as h:
					if create_rows is not None:
						h.set_return("create", create_rows)
					with mock.patch.object(run, "_log") as log:
						run.run_consolidation(execute=execute)

				self.assertEqual(log.call_args_list[-1].args[0], expected)

	def test_status_mapping_for_assignments_already_applied(self):
		assignments = [
			{"client_id": "1", "customer": "C1", "action": "already_applied"},
			{"client_id": "2", "customer": "C2", "action": "would_assign"},
			{"client_id": "3", "customer": "C3", "action": "skipped_live"},
		]
		with _Harness() as h:
			h.set_return("assign", assignments)
			rows, _note = run._run_assign(False)

		self.assertEqual([r["status"] for r in rows], ["already_applied", "pending", "skipped_live"])

	def test_status_mapping_for_merges(self):
		merges = [
			{"merge_from": "A", "merge_into": "B", "status": "pending", "action": "merged"},
			{"merge_from": "C", "merge_into": "D", "status": "already_applied", "action": "skipped"},
			{
				"merge_from": "E",
				"merge_into": "F",
				"status": "invalid",
				"action": "skipped",
				"reason": "no such customer",
			},
			{
				"merge_from": "G",
				"merge_into": "H",
				"status": "blocked",
				"action": "skipped",
				"unresolved_field_conflicts": ["tax_id"],
			},
			{"merge_from": "I", "merge_into": "J", "status": "pending", "action": "error", "error": "db"},
		]
		with _Harness() as h:
			h.set_return("merge", merges)
			rows, _note = run._run_merge(True)

		statuses = [r["status"] for r in rows]
		self.assertEqual(statuses, ["applied", "already_applied", "invalid", "blocked", "error"])
		self.assertIn("tax_id", rows[3]["reason"])
		self.assertEqual(run._count(rows)["invalid"], 1)
