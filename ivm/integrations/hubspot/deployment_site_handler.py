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
    DEPLOYMENT_SITE_TYPE_ID,
    HUBSPOT_DEAL_ID_FIELD,
    MACHINE_FIELD_MAPS,
    MACHINE_TYPE_TO_CHILD_DOCTYPE,
    MACHINE_TYPE_TO_CHILD_TABLE,
    MACHINE_TYPES_WITH_BINS,
    SITE_FIELD_MAP,
)
from ivm.integrations.hubspot.sync_utils import coerce_value, set_acting_user

_LOG = "hubspot"


@contextmanager
def _log_error(title: str):
    """Catch any exception, log it with a traceback, then suppress it."""
    try:
        yield
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


def handle_site_webhook(
    hubspot_site_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Re-sync a deployment site (properties + machines + bins) into its Deployment Location."""
    set_acting_user(hubspot_user_id)
    site_id_str = str(hubspot_site_id)

    crm_deal_name = _resolve_deal_for_site(site_id_str)
    if not crm_deal_name:
        return

    with _log_error(f"failed to sync deployment site {site_id_str}"):
        site_data = api.get_custom_object(
            DEPLOYMENT_SITE_TYPE_ID, site_id_str,
            properties=list(SITE_FIELD_MAP.keys()),
        )
        properties = site_data.get("properties", {})
        machines = _fetch_site_machines(site_id_str)

        _upsert_location_from_webhook(
            crm_deal_name, site_id_str, properties, machines,
        )
        frappe.logger(_LOG).info(
            f"Synced deployment site {site_id_str} to CRM Deal {crm_deal_name}"
        )


def handle_machine_webhook(
    machine_type_id: str,
    hubspot_machine_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Walk machine → site → deal and re-sync the parent site."""
    set_acting_user(hubspot_user_id)
    machine_id_str = str(hubspot_machine_id)

    site_ids = None
    with _log_error(
        f"failed to resolve site for machine {machine_id_str} "
        f"(type {machine_type_id})",
    ):
        site_ids = api.get_machine_site_ids(machine_type_id, machine_id_str)

    if site_ids is None:
        return

    if not site_ids:
        frappe.logger(_LOG).warning(
            f"No deployment site associated with machine {machine_id_str} "
            f"(type {machine_type_id}) — skipping"
        )
        return

    for site_id in site_ids:
        with _log_error(
            f"failed to sync site {site_id} after machine {machine_id_str} change",
        ):
            handle_site_webhook(site_id, hubspot_user_id=hubspot_user_id)


def handle_bin_webhook(
    hubspot_bin_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Walk bin → machine → site → deal and re-sync the parent site."""
    set_acting_user(hubspot_user_id)
    bin_id_str = str(hubspot_bin_id)

    machine_pairs = None
    with _log_error(f"failed to resolve machine for bin {bin_id_str}"):
        machine_pairs = api.get_bin_machine_ids(bin_id_str)

    if machine_pairs is None:
        return

    if not machine_pairs:
        frappe.logger(_LOG).warning(
            f"No machine associated with bin {bin_id_str} — skipping"
        )
        return

    for machine_type_id, machine_id in machine_pairs:
        with _log_error(
            f"failed to sync machine {machine_id} after bin {bin_id_str} change",
        ):
            handle_machine_webhook(
                machine_type_id, machine_id, hubspot_user_id=hubspot_user_id,
            )


def _resolve_deal_for_site(site_id: str) -> str | None:
    """Find the CRM Deal for a site via HubSpot associations, falling back to local lookup."""
    deal_ids: list = []
    with _log_error(f"failed to fetch deal associations for site {site_id}"):
        deal_ids = api.get_site_deal_ids(site_id)

    for deal_id in deal_ids:
        crm_deal_name = frappe.db.get_value(
            "CRM Deal", {HUBSPOT_DEAL_ID_FIELD: str(deal_id)}, "name",
        )
        if crm_deal_name:
            return crm_deal_name

    crm_deal = frappe.db.get_value(
        "Deployment Location", {"hubspot_site_id": site_id}, "crm_deal",
    )
    if crm_deal:
        return crm_deal

    frappe.logger(_LOG).warning(
        f"No CRM Deal found for deployment site {site_id} — skipping"
    )
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
) -> None:
    """Create or update a Deployment Location from webhook data."""
    existing_name = frappe.db.get_value(
        "Deployment Location", {"hubspot_site_id": hubspot_site_id}, "name",
    )

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
        loc.save(ignore_permissions=True)
    else:
        loc.insert(ignore_permissions=True)

    action = "Updated" if existing_name else "Created"
    frappe.logger(_LOG).info(
        f"{action} Deployment Location {loc.name} (HubSpot site {hubspot_site_id})"
    )


def fetch_all_deployment_sites(hubspot_deal_id: int | str) -> list[dict[str, Any]]:
    """Return site dicts for a deal, each with properties and machine associations."""
    hubspot_deal_id_str = str(hubspot_deal_id)

    association_ids: list = []
    with _log_error(
        f"failed to fetch deployment site associations for deal {hubspot_deal_id_str}",
    ):
        association_ids = api.get_deal_deployment_site_ids(hubspot_deal_id_str)

    if not association_ids:
        frappe.logger(_LOG).info(
            f"No deployment sites associated with HubSpot deal {hubspot_deal_id_str}"
        )
        return []

    sites: list[dict[str, Any]] = []

    for site_id in association_ids:
        with _log_error(
            f"failed to fetch deployment site {site_id} for deal {hubspot_deal_id_str}",
        ):
            site_data = api.get_custom_object(
                DEPLOYMENT_SITE_TYPE_ID, site_id, properties=list(SITE_FIELD_MAP.keys()),
            )
            properties = site_data.get("properties", {})
            machines = _fetch_site_machines(site_id)

            sites.append({
                "hubspot_site_id": str(site_id),
                "properties": properties,
                "machines": machines,
            })

    return sites


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
