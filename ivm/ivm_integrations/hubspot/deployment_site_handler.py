"""Fetch and map HubSpot deployment site data for syncing into Frappe."""

from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client
from ivm.ivm_integrations.hubspot.constants import (
    BIN_FIELD_MAP,
    DEPLOYMENT_SITE_TYPE_ID,
    MACHINE_FIELD_MAPS,
    MACHINE_TYPE_TO_CHILD_DOCTYPE,
    MACHINE_TYPE_TO_CHILD_TABLE,
    MACHINE_TYPES_WITH_BINS,
    SITE_FIELD_MAP,
)
from ivm.ivm_integrations.hubspot.sync_utils import coerce_value


def fetch_all_deployment_sites(hubspot_deal_id: int | str) -> list[dict[str, Any]]:
    """Return site dicts for a deal, each with properties and machine associations."""
    hubspot_deal_id_str = str(hubspot_deal_id)

    try:
        association_ids = hubspot_client.get_deal_deployment_site_ids(hubspot_deal_id_str)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch deployment site associations for deal {hubspot_deal_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return []

    if not association_ids:
        frappe.logger("hubspot").info(
            f"No deployment sites associated with HubSpot deal {hubspot_deal_id_str}"
        )
        return []

    sites: list[dict[str, Any]] = []

    for site_id in association_ids:
        try:
            site_data = hubspot_client.get_custom_object(
                DEPLOYMENT_SITE_TYPE_ID, site_id, properties=list(SITE_FIELD_MAP.keys()),
            )
            properties = site_data.get("properties", {})
            machines = _fetch_site_machines(site_id)

            sites.append({
                "hubspot_site_id": str(site_id),
                "properties": properties,
                "machines": machines,
            })
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to fetch deployment site {site_id} for deal {hubspot_deal_id_str}",
                message=frappe.get_traceback(with_context=True),
            )

    return sites


def _fetch_site_machines(site_id: int | str) -> dict[str, list[dict[str, Any]]]:
    """Return a dict mapping child table fieldnames to lists of machine row dicts."""
    machines: dict[str, list[dict[str, Any]]] = {}

    for machine_type_id, child_table in MACHINE_TYPE_TO_CHILD_TABLE.items():
        try:
            machine_ids = hubspot_client.get_site_machine_ids(site_id, machine_type_id)
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to fetch {child_table} associations for site {site_id}",
                message=frappe.get_traceback(with_context=True),
            )
            continue

        if not machine_ids:
            continue

        field_map = MACHINE_FIELD_MAPS.get(machine_type_id, {})
        child_doctype = MACHINE_TYPE_TO_CHILD_DOCTYPE.get(machine_type_id, "")
        rows: list[dict[str, Any]] = []

        for machine_id in machine_ids:
            try:
                machine_data = hubspot_client.get_machine(machine_type_id, machine_id)
                props = machine_data.get("properties", {})
                row = _map_machine_properties(props, field_map, child_doctype)

                if machine_type_id in MACHINE_TYPES_WITH_BINS:
                    bins_data = _fetch_machine_bins(machine_type_id, machine_id)
                    if bins_data:
                        row["bins_data"] = frappe.as_json(bins_data)

                rows.append(row)
            except Exception:
                frappe.log_error(
                    title=f"HubSpot: failed to fetch machine {machine_id} (type {machine_type_id})",
                    message=frappe.get_traceback(with_context=True),
                )

        if rows:
            machines[child_table] = rows

    return machines


def _map_machine_properties(
    properties: dict[str, Any],
    field_map: dict[str, str],
    child_doctype: str,
) -> dict[str, Any]:
    """Map HubSpot machine properties to Frappe child table field values."""
    meta = frappe.get_meta(child_doctype) if child_doctype else None
    row: dict[str, Any] = {}

    for hs_key, frappe_key in field_map.items():
        value = properties.get(hs_key)
        if value is None or value == "":
            continue

        df = meta.get_field(frappe_key) if meta else None
        row[frappe_key] = coerce_value(value, df)

    return row


def _fetch_machine_bins(
    machine_type_id: str,
    machine_id: int | str,
) -> list[dict[str, Any]]:
    """Fetch and map bin associations for a machine."""
    try:
        bin_ids = hubspot_client.get_machine_bin_ids(machine_type_id, machine_id)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch bin associations for machine {machine_id}",
            message=frappe.get_traceback(with_context=True),
        )
        return []

    if not bin_ids:
        return []

    bins: list[dict[str, Any]] = []

    for bin_id in bin_ids:
        try:
            bin_data = hubspot_client.get_bin(bin_id)
            props = bin_data.get("properties", {})
            mapped = {
                frappe_key: props[hs_key]
                for hs_key, frappe_key in BIN_FIELD_MAP.items()
                if props.get(hs_key) not in (None, "")
            }
            if mapped:
                bins.append(mapped)
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to fetch bin {bin_id} for machine {machine_id}",
                message=frappe.get_traceback(with_context=True),
            )

    return bins
