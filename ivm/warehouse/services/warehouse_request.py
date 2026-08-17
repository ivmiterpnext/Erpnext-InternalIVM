from typing import Any, NamedTuple

import frappe

from ivm.warehouse.services.machine import (
    apply_machine_data,
    fetch_machine,
)
from ivm.warehouse.services.pick_list import create_pick_list, delete_draft_pick_list


_COMMON_DETAIL_FIELDS = [
    "machine_name", "connectivity_type", "connectivity_device_quantity",
    "label_color", "offline_sales", "smartscreen", "workflow",
    "serial_validation", "home_screen_logo", "machine_type_id",
    "casters", "notes",
]

_LOCKER_SYNC_FIELDS = [
    "lan_ports", "plug_type", "interior_lighting",
    "bin_door_type", "3d_printed",
]

_VAULT_SYNC_FIELDS = [f for f in _LOCKER_SYNC_FIELDS if f != "3d_printed"]

class _TableConfig(NamedTuple):
    reason: str
    doctype: str
    extra_fields: list[str]


# Add a new entry here when a new deployment detail table is introduced.
_TABLE_CONFIG: dict[str, _TableConfig] = {
    "custom_deployment_smartstation_details": _TableConfig(
        reason="Build Machine",
        doctype="Deployment SmartStation Details",
        extra_fields=["card_reader_type", "machine_key"],
    ),
    "custom_deployment_smartlocker_details": _TableConfig(
        reason="Build Locker",
        doctype="Deployment SmartLocker Details",
        extra_fields=_LOCKER_SYNC_FIELDS,
    ),
    "custom_deployment_smartsync_details": _TableConfig(
        reason="Build Locker",
        doctype="Deployment SmartSync Details",
        extra_fields=_LOCKER_SYNC_FIELDS,
    ),
    "custom_deployment_smartvault_details": _TableConfig(
        reason="Build Vault",
        doctype="Deployment SmartVault Details",
        extra_fields=_VAULT_SYNC_FIELDS,
    ),
    "custom_deployment_smartcenter_details": _TableConfig(
        reason="Build Kiosk",
        doctype="Deployment SmartCenter Details",
        extra_fields=[
            "kiosk_options", "kvm_switch_options", "monitor_options",
            "network_options", "network_port_in_bins", "interior_kiosk_lighting",
            "locker_bin_door_type", "countertop_color", "ada_side_table",
            "kiosk_side_for_table", "monitor_mount", "power_connections_in_bins",
        ],
    ),
}


class _PendingRequest(NamedTuple):
    row: Any
    icorp_data: dict[str, Any]


@frappe.whitelist()
def create_build_requests_from_detail_rows(project_name: str, detail_table: str) -> dict:
    """
    Create one Warehouse Request per row in the given detail child table.
    All-or-nothing: if any iCorp lookup fails, no requests are created.
    """
    if detail_table not in _TABLE_CONFIG:
        frappe.throw(f"Unknown detail table: {detail_table}")

    config = _TABLE_CONFIG[detail_table]
    reason = config.reason
    project = frappe.get_doc("Project", project_name)
    rows = project.get(detail_table) or []

    if not rows:
        frappe.throw(f"No rows found in {detail_table} on project {project_name}.")

    customer_name = project.get("customer")
    if not customer_name:
        frappe.throw("Customer is not set on this Project. Cannot look up machines in iCorp.")

    client_id = frappe.db.get_value("Customer", customer_name, "icorp_client_id")
    if not client_id:
        frappe.throw(
            f'Customer "{customer_name}" does not have an iCorp Client ID. '
            "Please set it on the Customer record before generating build requests."
        )

    fields_to_copy = _COMMON_DETAIL_FIELDS + config.extra_fields

    # Pass 1 — validate all rows before creating anything.
    pending: list[_PendingRequest] = []
    failed: list[str] = []
    skipped = 0

    for row in rows:
        machine_name = row.get("machine_name") or row.name

        if frappe.db.exists("Warehouse Request", {
            "related_project": project_name,
            "request_reason": reason,
            "machine_name": machine_name,
        }):
            skipped += 1
            continue

        icorp_data = fetch_machine(machine_name, client_id)
        if icorp_data is None:
            failed.append(machine_name)
            continue

        pending.append(_PendingRequest(row=row, icorp_data=icorp_data))

    if failed:
        return {"created": [], "skipped": skipped, "failed": failed}

    # Pass 2 — all machines validated, safe to create.
    project_display = project.get("project_name") or project_name
    location_name = project_display.split(" - ")[0] if " - " in project_display else project_display

    created: list[str] = []

    for item in pending:
        row = item.row
        icorp_data = item.icorp_data
        machine_name = row.get("machine_name") or row.name

        wr = frappe.new_doc("Warehouse Request")
        wr.related_project = project_name
        wr.request_reason = reason
        wr.schema_version = 2
        wr.source_detail_doctype = config.doctype
        wr.source_detail_row = row.name
        wr.customer = customer_name
        wr.locale = project.get("locale")
        wr.machine_ownership_status = project.get("machine_ownership_status")
        wr.contact = project.get("contact_name")
        wr.created_by = frappe.session.user
        wr.created_date = frappe.utils.nowdate()
        wr.subject = f"{location_name} - {reason} [{machine_name}]"

        for field in fields_to_copy:
            value = row.get(field)
            if value is not None and value != "":
                setattr(wr, field, value)

        apply_machine_data(wr, icorp_data)
        wr.insert(ignore_permissions=True)
        created.append(wr.name)

    frappe.db.commit()
    return {"created": created, "skipped": skipped, "failed": []}


def _serialize_pick_list(pl_doc) -> dict:
    """Build a frontend-friendly representation of an existing Pick List."""
    is_draft = pl_doc.docstatus == 0

    items = []
    for loc in pl_doc.locations:
        if is_draft:
            available_qty = (
                frappe.db.get_value(
                    "Bin",
                    {"item_code": loc.item_code, "warehouse": loc.warehouse},
                    "actual_qty",
                ) or 0
            )
        else:
            available_qty = loc.stock_qty

        items.append({
            "row_name": loc.name,
            "item_code": loc.item_code,
            "item_name": loc.item_name,
            "warehouse": loc.warehouse,
            "qty": loc.qty,
            "picked_qty": loc.picked_qty,
            "uom": loc.uom,
            "available_qty": available_qty,
        })

    stock_entry = frappe.db.get_value(
        "Stock Entry", {"pick_list": pl_doc.name, "docstatus": ["!=", 2]}, "name"
    )

    return {
        "pick_list": pl_doc.name,
        "submitted": pl_doc.docstatus == 1,
        "target_warehouse": pl_doc.parent_warehouse,
        "stock_entry": stock_entry,
        "items": items,
    }


@frappe.whitelist()
def get_or_create_warehouse_request_pick_list(warehouse_request: str) -> dict:
    """Get the existing Pick List for a Warehouse Request, or create one if none exists."""
    pick_list = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")

    if pick_list:
        return _serialize_pick_list(frappe.get_doc("Pick List", pick_list))

    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
    )
    pl_name = create_pick_list(company)
    frappe.db.set_value("Warehouse Request", warehouse_request, "pick_list", pl_name)

    default_target_warehouse = _get_default_target_warehouse()
    if default_target_warehouse:
        frappe.db.set_value("Pick List", pl_name, "parent_warehouse", default_target_warehouse)

    return {
        "pick_list": pl_name,
        "submitted": False,
        "target_warehouse": default_target_warehouse,
        "items": [],
    }


@frappe.whitelist()
def get_warehouse_request_linked_docs(warehouse_request):
    """Return linked Pick List, Stock Entry, and Delivery Note in a single call."""
    pick_list = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")
    if not pick_list:
        return {"pick_list": None, "pick_list_submitted": False, "stock_entry": None, "delivery_note": None}

    docstatus = frappe.db.get_value("Pick List", pick_list, "docstatus")

    stock_entry = None
    delivery_note = None

    if docstatus == 1:
        stock_entry = frappe.db.get_value(
            "Stock Entry", {"pick_list": pick_list, "docstatus": ["!=", 2]}, "name"
        )
        delivery_note = frappe.db.get_value(
            "Delivery Note",
            {"custom_related_warehouse_request": warehouse_request, "docstatus": ["!=", 2]},
            "name",
        )

    return {
        "pick_list": pick_list,
        "pick_list_submitted": docstatus == 1,
        "stock_entry": stock_entry,
        "delivery_note": delivery_note,
    }


@frappe.whitelist()
def reset_warehouse_request_pick_list(warehouse_request):
    """Delete the draft Pick List for a Warehouse Request and clear the link."""
    pl_name = frappe.db.get_value("Warehouse Request", warehouse_request, "pick_list")

    if not pl_name:
        return {"success": False, "message": "No pick list linked"}

    frappe.db.set_value("Warehouse Request", warehouse_request, "pick_list", None)
    delete_draft_pick_list(pl_name)

    return {"success": True}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def warehouse_request_query(doctype, txt, searchfield, start, page_len, filters):
    return frappe.db.sql("""
        SELECT
            name,
            CASE
                WHEN subject IS NOT NULL AND subject != ''
                THEN CONCAT(name, ' - ', subject)
                ELSE name
            END as description
        FROM `tabWarehouse Request`
        WHERE
            (name LIKE %(txt)s OR subject LIKE %(txt)s)
            AND docstatus < 2
        ORDER BY modified DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        'txt': f'%{txt}%',
        'start': start,
        'page_len': page_len
    })


DEFAULT_TARGET_WAREHOUSE = "Build In Progress - I"


def _get_default_target_warehouse():
    if frappe.db.exists("Warehouse", DEFAULT_TARGET_WAREHOUSE):
        return DEFAULT_TARGET_WAREHOUSE
    return None


@frappe.whitelist()
def create_shipping_request_from_build(build_warehouse_request):
    build_wr = frappe.get_doc("Warehouse Request", build_warehouse_request)

    if not build_wr.request_reason or not build_wr.request_reason.startswith("Build"):
        frappe.throw(f"Warehouse Request {build_warehouse_request} is not a Build request.")

    if build_wr.status != "Crated - Ready to Ship":
        frappe.throw(
            f"Warehouse Request {build_warehouse_request} must be in "
            "'Crated - Ready to Ship' status to create a Shipping Request."
        )

    if not build_wr.pick_list:
        frappe.throw(f"Warehouse Request {build_warehouse_request} has no Pick List.")

    pl_docstatus = frappe.db.get_value("Pick List", build_wr.pick_list, "docstatus")
    if pl_docstatus != 1:
        frappe.throw(
            f"Pick List {build_wr.pick_list} must be submitted before "
            "creating a Shipping Request."
        )

    existing = frappe.db.get_value(
        "Warehouse Request",
        {"source_build_request": build_warehouse_request, "request_reason": "Shipping Request"},
        "name",
    )
    if existing:
        frappe.msgprint(
            f'Shipping Request <a href="/app/warehouse-request/{existing}">{existing}</a> '
            "already exists for this Build.",
            title="Shipping Request Exists",
            indicator="blue",
        )
        return existing

    shipping_wr = frappe.new_doc("Warehouse Request")
    shipping_wr.request_reason = "Shipping Request"
    shipping_wr.source_build_request = build_warehouse_request
    shipping_wr.related_project = build_wr.related_project
    shipping_wr.customer = build_wr.customer
    shipping_wr.status = "New"
    shipping_wr.subject = f"Ship {build_wr.request_reason} - {build_wr.name}"
    shipping_wr.insert(ignore_permissions=True)

    return shipping_wr.name

# Following will be replaced and push directly to iCorp
def _build_equipment_info_description(wr) -> str:
    lines = [
        f"Equipment Information Has Been Added to {wr.name}",
        "",
        f"Project: {wr.subject or ''} {wr.machine_name or ''}",
        "",
        f"Machine Name: {wr.machine_name or ''}",
        f"PROSE Number: {wr.prose_number or ''}",
        f"Serial Number: {wr.serial_number or ''}",
        f"LAN MAC Address: {wr.lan_mac_address or ''}",
        f"WiFi MAC Address: {wr.wifi_mac_address or ''}",
    ]

    rfid_rows = wr.get("rfid_settings") or []
    if rfid_rows:
        lines.append("")
        for idx, row in enumerate(rfid_rows, start=1):
            lines.append(
                f"RFID Setting {idx}: "
                f"Facility Code Start {row.facility_code_start_position}, "
                f"Facility Code Length {row.facility_code_length}, "
                f"Employee ID Start {row.employee_id_start_position}, "
                f"Employee ID Length {row.employee_id_length}, "
                f"Target Number Base {row.target_number_base}, "
                f"Bit Size {row.bit_size}, "
                f"Bit Reverse {'Yes' if row.bit_reverse_feature else 'No'}"
            )

    return "<br>".join(lines)


@frappe.whitelist()
def get_equipment_info_task(warehouse_request):
    """Return the existing 'add machine info' Task linked to this Warehouse Request, if any."""
    return frappe.db.get_value(
        "Task",
        {"custom_warehouse_request": warehouse_request, "type": "add machine info"},
        "name",
    )


@frappe.whitelist()
def send_equipment_info_to_ics(warehouse_request):
    """Create the 'Add Equipment Information' Task for a schema v2 Warehouse Request,
    pulling data from the single-machine schema fields instead of the legacy
    numbered/ordinal fields used by schema_version == 1.
    """
    wr = frappe.get_doc("Warehouse Request", warehouse_request)

    if (wr.schema_version or 0) < 2:
        frappe.throw("This action is only available for the new (schema v2) Warehouse Request layout.")

    if not (wr.request_reason or "").startswith("Build"):
        frappe.throw("This action is only available for Build requests.")

    existing = get_equipment_info_task(warehouse_request)
    if existing:
        return existing

    task = frappe.get_doc({
        "doctype": "Task",
        "subject": f"Add Equipment Information into CSS for {wr.machine_name} and {wr.customer}",
        "status": "Open",
        "type": "add machine info",
        "custom_customer": wr.customer,
        "project": wr.related_project,
        "custom_warehouse_request": wr.name,
        "custom_assigned_to": wr.created_by,
        "description": _build_equipment_info_description(wr),
    })
    task.insert(ignore_permissions=True)
    frappe.db.commit()

    return task.name
