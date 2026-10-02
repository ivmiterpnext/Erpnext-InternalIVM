"""HubSpot reconciliation job.

Runs every 15 minutes (see hooks.py scheduler_events["cron"]). For each
object type in routing.SYNC_TARGETS, searches HubSpot for records modified
since the stored checkpoint (HubSpot Reconciler Settings.last_checkpoint)
and routes each hit through routing.route() — the same dispatch the webhook
receiver uses in webhook.py. This exists to catch anything a webhook
missed: a HubSpot delivery gap, the credential-rotation window during the
bundled-app cutover, or any other dropped event. It is not a substitute for
webhooks (webhooks remain the primary, near-real-time path) — this is a
15-minute-lag safety net.

Checkpoint semantics
---------------------
The checkpoint only advances once a run completes (successfully or with
per-object-type errors isolated and logged — see below). If reconcile()
itself raises before reaching the checkpoint update, the next run starts
from the same (unmoved) checkpoint and simply re-scans a wider window, so
no window is ever silently skipped.

A SAFETY_LAG_MINUTES is subtracted from "now" every time the checkpoint
advances, because HubSpot's own search index can lag slightly behind
real-time writes (HubSpot's docs: "it may take a few moments for newly
created or updated CRM objects to appear in search results"). Without this
lag, a record written moments after this run's search queries executed
could fall in the gap between this run's "now" and the next run's start,
and be permanently missed. The lag means every run deliberately re-scans
the last SAFETY_LAG_MINUTES of the previous window — redundant, but cheap:
routing.route() dedupes via enqueue_sync's per-record job IDs, and every
sync handler re-reads full current HubSpot state regardless of which
property changed, so re-routing an unchanged record is a harmless no-op.

The checkpoint is NOT set automatically on install — HubSpot Reconciler
Settings.last_checkpoint must be set by hand before this job does
anything. An unset checkpoint is a deliberate no-op, not an error, so
shipping this code ahead of the actual cutover is safe.

Per-object-type error isolation
---------------------------------
One object type's search failing (rate limit exhaustion, a transient
HubSpot 5xx, a scope issue) does not stop the other 14 from being
scanned, and does not block the checkpoint from advancing — a
persistently-broken object type would otherwise wedge reconciliation for
every other (working) object type too. Failures are logged individually
to the Error Log and summarized on HubSpot Reconciler Settings so they're
visible without digging through logs.
"""

from __future__ import annotations

import time
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime
from frappe.utils.data import get_system_timezone

from ivm.integrations.hubspot import api, routing
from ivm.integrations.hubspot.constants import (
	COMPANY_TYPE_ID,
	CONTACT_TYPE_ID,
	DEAL_TYPE_ID,
	ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID,
)

_LOG = "hubspot"

SAFETY_LAG_MINUTES = 5
_PAGE_SIZE = 100
_MAX_PAGES_PER_TYPE = 100  # 100 * 100 = 10,000 = HubSpot's search result cap
_INTER_PAGE_SLEEP_SECONDS = 0.25

_STANDARD_SEARCH_PATHS: dict[str, str] = {
	DEAL_TYPE_ID: "deals",
	CONTACT_TYPE_ID: "contacts",
	COMPANY_TYPE_ID: "companies",
}


def _search_path(object_type_id: str) -> str:
	"""Resolve the {objectType} path segment for the v3 CRM search endpoint.

	Standard objects use a plural name, engagements use their own plural
	name, and custom objects accept their numeric type ID directly (all
	per HubSpot's CRM Search API docs).
	"""
	if object_type_id in _STANDARD_SEARCH_PATHS:
		return _STANDARD_SEARCH_PATHS[object_type_id]
	if object_type_id in ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID:
		return ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID[object_type_id]
	return object_type_id


def _last_modified_property(object_type_id: str) -> str:
	"""HubSpot's "last modified" property is named differently only for
	contacts (``lastmodifieddate``); every other object type — companies,
	deals, custom objects, and engagements — uses ``hs_lastmodifieddate``.
	"""
	return "lastmodifieddate" if object_type_id == CONTACT_TYPE_ID else "hs_lastmodifieddate"


def _to_epoch_ms(value) -> int:
	"""Convert a Frappe Datetime value (naive, in the site's configured
	system timezone) to a UTC epoch-millisecond integer, as HubSpot's
	search API filters require.
	"""
	naive = get_datetime(value)
	localized = naive.replace(tzinfo=ZoneInfo(get_system_timezone()))
	return int(localized.timestamp() * 1000)


def reconcile() -> None:
	"""Entry point called every 15 minutes by the scheduler."""
	settings = frappe.get_single("HubSpot Reconciler Settings")

	if not settings.last_checkpoint:
		frappe.logger(_LOG).info(
			"HubSpot reconciler: last_checkpoint is not set on HubSpot Reconciler "
			"Settings — skipping run. Set it to enable reconciliation."
		)
		return

	run_started_at = now_datetime()

	try:
		checkpoint_epoch_ms = _to_epoch_ms(settings.last_checkpoint)
	except Exception:
		frappe.log_error(
			title="HubSpot reconciler: invalid last_checkpoint value",
			message=frappe.get_traceback(with_context=True),
		)
		return

	results: dict[str, dict[str, int]] = {}
	failed_object_types: list[str] = []

	for object_type_id in routing.SYNC_TARGETS:
		try:
			results[object_type_id] = _reconcile_object_type(object_type_id, checkpoint_epoch_ms)
		except Exception:
			failed_object_types.append(object_type_id)
			frappe.log_error(
				title=f"HubSpot reconciler: failed scanning object type {object_type_id}",
				message=frappe.get_traceback(with_context=True),
			)

	new_checkpoint = add_to_date(run_started_at, minutes=-SAFETY_LAG_MINUTES)
	settings.last_checkpoint = new_checkpoint
	settings.last_run_at = run_started_at
	settings.last_run_status = "Failed" if failed_object_types else "Success"
	settings.last_run_error = (
		f"Object types that failed to scan this run: {failed_object_types}" if failed_object_types else ""
	)
	settings.save(ignore_permissions=True)
	frappe.db.commit()

	frappe.logger(_LOG).info(
		f"HubSpot reconciler run complete. Results by object type: {results}. "
		f"Failed: {failed_object_types or 'none'}. New checkpoint: {new_checkpoint}."
	)


def _reconcile_object_type(object_type_id: str, checkpoint_epoch_ms: int) -> dict[str, int]:
	"""Search one object type for records modified since the checkpoint,
	routing each hit through routing.route(). Returns a count of routing
	outcomes (e.g. {"enqueued": 3, "dropped": 1}).
	"""
	search_path = _search_path(object_type_id)
	prop_name = _last_modified_property(object_type_id)
	filters = [{"propertyName": prop_name, "operator": "GT", "value": str(checkpoint_epoch_ms)}]

	counts: dict[str, int] = {}
	after = None

	for _page in range(_MAX_PAGES_PER_TYPE):
		response = api.search_objects(search_path, filters, after=after, limit=_PAGE_SIZE)

		for row in response.get("results", []):
			object_id = row.get("id")
			if not object_id:
				continue
			outcome = routing.route(object_type_id, str(object_id))
			counts[outcome] = counts.get(outcome, 0) + 1

		after = response.get("paging", {}).get("next", {}).get("after")
		if not after:
			break
		time.sleep(_INTER_PAGE_SLEEP_SECONDS)
	else:
		frappe.logger(_LOG).warning(
			f"HubSpot reconciler: object type {object_type_id} hit the "
			f"{_MAX_PAGES_PER_TYPE * _PAGE_SIZE}-result search cap this run — "
			f"some modified records in this window may not have been scanned. "
			f"This means more than {_MAX_PAGES_PER_TYPE * _PAGE_SIZE} records of this "
			f"type changed since the last checkpoint; investigate before trusting "
			f"this object type's coverage."
		)

	return counts
