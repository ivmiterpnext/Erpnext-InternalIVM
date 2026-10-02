"""Fetch and map HubSpot deployment site data for syncing into Frappe.

Provides both batch-fetch helpers (used by deal_handler during full deal
syncs) and individual webhook handlers for generic webhook subscriptions
on deployment sites, machines, and bins.
"""

from contextlib import contextmanager
from typing import Any

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
	BIN_FIELD_MAP,
	BIN_TYPE_ID,
	DEPLOYMENT_SITE_TYPE_ID,
	HUBSPOT_DEAL_ID_FIELD,
	MACHINE_FIELD_MAPS,
	MACHINE_TYPE_TO_CHILD_DOCTYPE,
	MACHINE_TYPE_TO_CHILD_TABLE,
	MACHINE_TYPES_WITH_BINS,
	SITE_FIELD_MAP,
)
from ivm.integrations.hubspot.sync_utils import (
	ConcurrentCreateConflict,
	coerce_value,
	enqueue_sync,
	retry_via_reenqueue,
	save_doc,
	set_acting_user,
)

_LOG = "hubspot"


@contextmanager
def _log_error(title: str):
	"""Catch any exception, log it with a traceback, then suppress it.

	HubSpotRateLimitExhausted and ConcurrentCreateConflict are re-raised so
	callers can handle re-enqueueing.
	"""
	try:
		yield
	except (api.HubSpotRateLimitExhausted, ConcurrentCreateConflict):
		raise
	except Exception:
		frappe.log_error(
			title=f"HubSpot: {title}",
			message=frappe.get_traceback(with_context=True),
		)


def _map_properties(
	properties: dict[str, Any],
	field_map: dict[str, str],
	meta: Any | None = None,
) -> dict[str, Any]:
	"""Map HubSpot properties to Frappe field values using *field_map*.

	Skips ``None``/empty values and coerces via ``coerce_value`` when a
	matching field definition is available in *meta*.
	"""
	row: dict[str, Any] = {}
	for hs_key, frappe_key in field_map.items():
		value = properties.get(hs_key)
		if value is None or value == "":
			continue
		df = meta.get_field(frappe_key) if meta else None
		row[frappe_key] = coerce_value(value, df)
	return row


@retry_via_reenqueue(object_type_id=DEPLOYMENT_SITE_TYPE_ID, id_kwarg="hubspot_site_id")
def sync_site(
	hubspot_site_id: int | str,
	attempt: int = 0,
) -> None:
	"""Re-sync a deployment site (properties + machines + bins) into its Deployment Location."""
	set_acting_user()
	site_id_str = str(hubspot_site_id)

	crm_deal_name = _resolve_deal_for_site(site_id_str)
	if not crm_deal_name:
		return

	_sync_site_core(site_id_str, crm_deal_name, trigger_deal_sync=True)


def _sync_site_core(
	hubspot_site_id: str,
	crm_deal_name: str,
	*,
	trigger_deal_sync: bool,
) -> None:
	"""Fetch and upsert a single deployment site into its Deployment Location.

	No blanket exception handling here (per R2) — callers (sync_site, or the
	inline Won-ordering step in deal_handler._sync_deal_core) are responsible
	for what happens on failure.

	If this creates a brand-new Deployment Location and trigger_deal_sync is
	True, enqueues a follow-up sync of the owning deal (e.g. a newly-arrived
	location should trigger the deal to re-evaluate Won status). Pass
	trigger_deal_sync=False when calling this from inside a deal sync that's
	already in progress, to avoid enqueueing a redundant self-resync.
	"""
	site_data = api.get_custom_object(
		DEPLOYMENT_SITE_TYPE_ID,
		hubspot_site_id,
		properties=list(SITE_FIELD_MAP.keys()),
	)
	properties = site_data.get("properties", {})
	machines = _fetch_site_machines(hubspot_site_id)

	is_new = _upsert_location_from_webhook(
		crm_deal_name,
		hubspot_site_id,
		properties,
		machines,
	)
	frappe.logger(_LOG).info(f"Synced deployment site {hubspot_site_id} to CRM Deal {crm_deal_name}")

	if is_new and trigger_deal_sync:
		hubspot_deal_id = frappe.db.get_value("CRM Deal", crm_deal_name, HUBSPOT_DEAL_ID_FIELD)
		if hubspot_deal_id:
			from ivm.integrations.hubspot.constants import DEAL_TYPE_ID
			from ivm.integrations.hubspot.deal_handler import sync_deal

			enqueue_sync(
				f"{sync_deal.__module__}.{sync_deal.__name__}",
				DEAL_TYPE_ID,
				str(hubspot_deal_id),
				hubspot_deal_id=str(hubspot_deal_id),
			)


@retry_via_reenqueue(
	type_kwarg="machine_type_id",
	id_kwarg="hubspot_machine_id",
)
def sync_machine(
	machine_type_id: str,
	hubspot_machine_id: int | str,
	attempt: int = 0,
) -> None:
	"""Walk machine → site and enqueue a sync of each associated site."""
	set_acting_user()
	machine_id_str = str(hubspot_machine_id)

	site_ids = api.get_machine_site_ids(machine_type_id, machine_id_str)

	if not site_ids:
		frappe.logger(_LOG).warning(
			f"No deployment site associated with machine {machine_id_str} (type {machine_type_id}) — skipping"
		)
		return

	for site_id in site_ids:
		enqueue_sync(
			"ivm.integrations.hubspot.deployment_site_handler.sync_site",
			DEPLOYMENT_SITE_TYPE_ID,
			str(site_id),
			hubspot_site_id=str(site_id),
		)


@retry_via_reenqueue(
	object_type_id=BIN_TYPE_ID,
	id_kwarg="hubspot_bin_id",
)
def sync_bin(
	hubspot_bin_id: int | str,
	attempt: int = 0,
) -> None:
	"""Walk bin → machine and enqueue a sync of each associated machine."""
	set_acting_user()
	bin_id_str = str(hubspot_bin_id)

	machine_pairs = api.get_bin_machine_ids(bin_id_str)

	if not machine_pairs:
		frappe.logger(_LOG).warning(f"No machine associated with bin {bin_id_str} — skipping")
		return

	for machine_type_id, machine_id in machine_pairs:
		enqueue_sync(
			"ivm.integrations.hubspot.deployment_site_handler.sync_machine",
			machine_type_id,
			str(machine_id),
			machine_type_id=machine_type_id,
			hubspot_machine_id=str(machine_id),
		)


def _resolve_deal_for_site(site_id: str) -> str | None:
	"""Find the CRM Deal for a site via HubSpot associations, falling back to local lookup.

	Self-heals by creating the CRM Deal if HubSpot has at least one deal
	association for this site but no local CRM Deal record matches yet
	(e.g. the deal's own object.creation event hasn't been processed yet).

	May raise ConcurrentCreateConflict or api.HubSpotRateLimitExhausted —
	the caller (sync_site) handles re-enqueueing.
	"""
	from ivm.integrations.hubspot.deal_handler import ensure_deal_exists

	deal_ids: list = []
	with _log_error(f"failed to fetch deal associations for site {site_id}"):
		deal_ids = api.get_site_deal_ids(site_id)

	for deal_id in deal_ids:
		crm_deal_name = frappe.db.get_value(
			"CRM Deal",
			{HUBSPOT_DEAL_ID_FIELD: str(deal_id)},
			"name",
		)
		if crm_deal_name:
			return crm_deal_name

	crm_deal = frappe.db.get_value(
		"Deployment Location",
		{"hubspot_site_id": site_id},
		"crm_deal",
	)
	if crm_deal:
		return crm_deal

	if deal_ids:
		return ensure_deal_exists(deal_ids[0])

	frappe.logger(_LOG).warning(f"No CRM Deal found for deployment site {site_id} — skipping")
	return None


def _apply_site_properties(loc: Any, site_properties: dict[str, Any]) -> None:
	"""Apply mapped HubSpot site properties to a Deployment Location."""
	meta = frappe.get_meta("Deployment Location")
	for key, value in _map_properties(site_properties, SITE_FIELD_MAP, meta).items():
		loc.set(key, value)


def _apply_machine_data(
	loc: Any,
	machines: dict[str, list[dict[str, Any]]],
) -> None:
	"""Replace all machine child tables on the Deployment Location."""
	for child_table in set(MACHINE_TYPE_TO_CHILD_TABLE.values()):
		loc.set(child_table, [])

	for child_table, rows in machines.items():
		for row in rows:
			if row:
				loc.append(child_table, row)


def _upsert_location_from_webhook(
	crm_deal_name: str,
	hubspot_site_id: str,
	site_properties: dict[str, Any],
	machines: dict[str, list[dict[str, Any]]],
) -> bool:
	"""Create or update a Deployment Location from webhook data.

	Returns True if a new Deployment Location was created, False if updated.
	"""
	existing_name = frappe.db.get_value(
		"Deployment Location",
		{"hubspot_site_id": hubspot_site_id},
		"name",
	)

	is_new = existing_name is None

	if existing_name:
		loc = frappe.get_doc("Deployment Location", existing_name)
	else:
		loc = frappe.new_doc("Deployment Location")
		loc.crm_deal = crm_deal_name
		loc.hubspot_site_id = hubspot_site_id

	_apply_site_properties(loc, site_properties)

	if not loc.location_name:
		loc.location_name = f"Site {hubspot_site_id}"

	_apply_machine_data(loc, machines)

	if existing_name:
		save_doc(loc, "site")
	else:
		loc.insert(ignore_permissions=True)

	action = "Updated" if existing_name else "Created"
	frappe.logger(_LOG).info(f"{action} Deployment Location {loc.name} (HubSpot site {hubspot_site_id})")

	return is_new


def _fetch_site_machines(site_id: int | str) -> dict[str, list[dict[str, Any]]]:
	"""Return ``{child_table: [row_dict, ...]}`` for all machine types on a site."""
	machines: dict[str, list[dict[str, Any]]] = {}

	for machine_type_id, child_table in MACHINE_TYPE_TO_CHILD_TABLE.items():
		machine_ids: list = []
		with _log_error(
			f"failed to fetch {child_table} associations for site {site_id}",
		):
			machine_ids = api.get_site_machine_ids(site_id, machine_type_id)

		if not machine_ids:
			continue

		field_map = MACHINE_FIELD_MAPS.get(machine_type_id, {})
		child_doctype = MACHINE_TYPE_TO_CHILD_DOCTYPE.get(machine_type_id, "")
		meta = frappe.get_meta(child_doctype) if child_doctype else None
		rows: list[dict[str, Any]] = []

		for machine_id in machine_ids:
			with _log_error(
				f"failed to fetch machine {machine_id} (type {machine_type_id})",
			):
				machine_data = api.get_machine(machine_type_id, machine_id)
				props = machine_data.get("properties", {})
				row = _map_properties(props, field_map, meta)

				if machine_type_id in MACHINE_TYPES_WITH_BINS:
					bins_data = _fetch_machine_bins(machine_type_id, machine_id)
					if bins_data:
						row["bins_data"] = frappe.as_json(bins_data)

				rows.append(row)

		if rows:
			machines[child_table] = rows

	return machines


def _fetch_machine_bins(
	machine_type_id: str,
	machine_id: int | str,
) -> list[dict[str, Any]]:
	"""Fetch bins for a machine, sorted by HubSpot creation time."""
	bin_ids: list = []
	with _log_error(f"failed to fetch bin associations for machine {machine_id}"):
		bin_ids = api.get_machine_bin_ids(machine_type_id, machine_id)

	if not bin_ids:
		return []

	# Pair each bin with its createdAt timestamp to preserve creation order.
	bins_with_ts: list[tuple[str, dict[str, Any]]] = []

	for bin_id in bin_ids:
		with _log_error(f"failed to fetch bin {bin_id} for machine {machine_id}"):
			bin_data = api.get_bin(bin_id)
			created_at = bin_data.get("createdAt", "")
			props = bin_data.get("properties", {})
			mapped = _map_properties(props, BIN_FIELD_MAP)
			if mapped:
				bins_with_ts.append((created_at, mapped))

	bins_with_ts.sort(key=lambda t: t[0])

	return [b for _, b in bins_with_ts]
