"""iCorp machine lookup for Warehouse Request generation."""

from __future__ import annotations

from typing import Any

import frappe

from ivm.integrations.icorp import icorp_api_get

_LOG = "ivm.warehouse.machine"


def _fetch_machine_by_name(machine_name: str) -> dict[str, Any] | None:
    response = icorp_api_get(f"SV/Machine/GetByName?name={machine_name}")
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return data[0] if data else None
    return None


def fetch_machine(machine_name: str, client_id: str) -> dict[str, Any] | None:
    """Look up a machine by name in iCorp and validate it belongs to the expected client.

    Returns a dict with icorp_machine_id, serial_number, and prose_number,
    or None if the machine is not found or the client does not match.
    """
    try:
        machine = _fetch_machine_by_name(machine_name)

        if not machine:
            frappe.logger(_LOG).warning(
                f"No machine found in iCorp for name {machine_name!r}"
            )
            return None

        if machine.get("client_id") != int(client_id):
            frappe.logger(_LOG).warning(
                f"Machine {machine_name!r} found in iCorp but belongs to client "
                f"{machine.get('client_id')}, expected {client_id}"
            )
            return None

        return {
            "icorp_machine_id": machine.get("id"),
            "serial_number": machine.get("serial_number"),
            "prose_number": machine.get("board_serial_number"),
        }

    except Exception:
        frappe.logger(_LOG).error(
            f"iCorp API error looking up machine {machine_name!r}: "
            f"{frappe.get_traceback()}"
        )
        return None


def apply_machine_data(wr: "frappe._dict", data: dict[str, Any]) -> None:
    """Set machine fields on a Warehouse Request doc from iCorp data."""
    for field in ("icorp_machine_id", "serial_number", "prose_number"):
        value = data.get(field)
        if value:
            setattr(wr, field, value)
