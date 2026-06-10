"""Fetch and map HubSpot deployment site data for syncing into Frappe.

Provides both batch-fetch helpers (used by deal_handler during full deal
syncs) and individual webhook handlers for generic webhook subscriptions
on deployment sites, machines, and bins.
"""

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

_LOG = "hubspot"


# ---------------------------------------------------------------------------
# Webhook entry points (called via frappe.enqueue from webhook.py)
# ---------------------------------------------------------------------------


def handle_site_webhook(
    hubspot_site_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Handle a deployment site creation or property change webhook.

    Finds the associated deal, then re-syncs the full site (properties +
    all machines + bins) into the matching Deployment Location.
    """
    from ivm.ivm_integrations.hubspot.sync_utils import set_acting_user

    set_acting_user(hubspot_user_id)
    site_id_str = str(hubspot_site_id)

    crm_deal_name = _resolve_deal_for_site(site_id_str)
    if not crm_deal_name:
        return

    try:
        site_data = hubspot_client.get_custom_object(
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
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to sync deployment site {site_id_str}",
            message=frappe.get_traceback(with_context=True),
        )


def handle_machine_webhook(
    machine_type_id: str,
    hubspot_machine_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Handle a machine (SmartStation/Locker/Sync/Vault/Center) webhook.

    Walks up the association chain: machine → site → deal, then re-syncs
    the entire site to keep the Deployment Location consistent.
    """
    from ivm.ivm_integrations.hubspot.sync_utils import set_acting_user

    set_acting_user(hubspot_user_id)
    machine_id_str = str(hubspot_machine_id)

    # Find the parent deployment site
    try:
        site_ids = hubspot_client.get_machine_site_ids(machine_type_id, machine_id_str)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to resolve site for machine {machine_id_str} "
                  f"(type {machine_type_id})",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not site_ids:
        frappe.logger(_LOG).warning(
            f"No deployment site associated with machine {machine_id_str} "
            f"(type {machine_type_id}) — skipping"
        )
        return

    # Re-sync each parent site (typically one)
    for site_id in site_ids:
        try:
            handle_site_webhook(site_id, hubspot_user_id=hubspot_user_id)
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to sync site {site_id} after machine "
                      f"{machine_id_str} change",
                message=frappe.get_traceback(with_context=True),
            )


def handle_bin_webhook(
    hubspot_bin_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Handle a bin creation or property change webhook.

    Walks up: bin → machine → site → deal, then re-syncs the site.
    """
    from ivm.ivm_integrations.hubspot.sync_utils import set_acting_user

    set_acting_user(hubspot_user_id)
    bin_id_str = str(hubspot_bin_id)

    # Find the parent machine
    try:
        machine_pairs = hubspot_client.get_bin_machine_ids(bin_id_str)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to resolve machine for bin {bin_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not machine_pairs:
        frappe.logger(_LOG).warning(
            f"No machine associated with bin {bin_id_str} — skipping"
        )
        return

    # Delegate to the machine handler for each parent
    for machine_type_id, machine_id in machine_pairs:
        try:
            handle_machine_webhook(
                machine_type_id, machine_id, hubspot_user_id=hubspot_user_id,
            )
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to sync machine {machine_id} after bin "
                      f"{bin_id_str} change",
                message=frappe.get_traceback(with_context=True),
            )


# ---------------------------------------------------------------------------
# Internal helpers for webhook handlers
# ---------------------------------------------------------------------------


def _resolve_deal_for_site(site_id: str) -> str | None:
    """Find the CRM Deal name for a deployment site via HubSpot associations.

    Falls back to looking up a local Deployment Location record if the
    HubSpot association lookup fails.
    """
    # Try HubSpot association first
    try:
        deal_ids = hubspot_client.get_site_deal_ids(site_id)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch deal associations for site {site_id}",
            message=frappe.get_traceback(with_context=True),
        )
        deal_ids = []

    for deal_id in deal_ids:
        crm_deal_name = frappe.db.get_value(
            "CRM Deal", {"custom_hubspot_deal_id": str(deal_id)}, "name",
        )
        if crm_deal_name:
            return crm_deal_name

    # Fallback: check if we already have a Deployment Location for this site
    crm_deal = frappe.db.get_value(
        "Deployment Location", {"hubspot_site_id": site_id}, "crm_deal",
    )
    if crm_deal:
        return crm_deal

    frappe.logger(_LOG).warning(
        f"No CRM Deal found for deployment site {site_id} — skipping"
    )
    return None


def _upsert_location_from_webhook(
    crm_deal_name: str,
    hubspot_site_id: str,
    site_properties: dict[str, Any],
    machines: dict[str, list[dict[str, Any]]],
) -> None:
    """Create or update a Deployment Location from webhook data.

    Similar to deal_handler._upsert_location but without target_ship_date
    calculation (that remains a deal-level concern).
    """
    from ivm.ivm_integrations.hubspot.deal_handler import (
        _apply_machine_data,
        _apply_site_properties,
    )

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
        frappe.logger(_LOG).info(f"Updated Deployment Location {existing_name}")
    else:
        loc.insert(ignore_permissions=True)
        frappe.logger(_LOG).info(
            f"Created Deployment Location {loc.name} (HubSpot site {hubspot_site_id})"
        )


# ---------------------------------------------------------------------------
# Batch fetch helpers (used by deal_handler for full deal syncs)
# ---------------------------------------------------------------------------


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

    # Collect bins with their HubSpot createdAt timestamp so we can
    # preserve the original creation order (the associations API does
    # not guarantee any particular ordering).
    bins_with_ts: list[tuple[str, dict[str, Any]]] = []

    for bin_id in bin_ids:
        try:
            bin_data = hubspot_client.get_bin(bin_id)
            created_at = bin_data.get("createdAt", "")
            props = bin_data.get("properties", {})
            mapped = {
                frappe_key: props[hs_key]
                for hs_key, frappe_key in BIN_FIELD_MAP.items()
                if props.get(hs_key) not in (None, "")
            }
            if mapped:
                bins_with_ts.append((created_at, mapped))
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to fetch bin {bin_id} for machine {machine_id}",
                message=frappe.get_traceback(with_context=True),
            )

    # Sort by createdAt (ISO-8601 string, lexicographic sort works) to
    # match the order bins were added in HubSpot.
    bins_with_ts.sort(key=lambda t: t[0])

    return [b for _, b in bins_with_ts]
