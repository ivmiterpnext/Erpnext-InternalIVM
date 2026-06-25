"""Fetch machine hardware data from iCorp.

Queries the MachineHardwareConfiguration, Machine, and Board endpoints
to populate serial number, PROSE number, MAC address, and RFID settings
for Warehouse Request generation.
"""

from __future__ import annotations

from typing import Any

import frappe

from ivm.integrations.icorp import icorp_api_get

_LOG = "ivm.warehouse.hardware_configuration"

# Each prefix maps to one set of RFID fields on the Board response.
# After icorp_api_get converts camelCase → snake_case, Board columns become
# e.g. "primary_facility_code_start_position".
_RFID_PREFIXES = (
    "primary",
    "secondary",
    "setting3_rfid",
    "setting4_rfid",
    "setting5_rfid",
)

# Maps the suffix on the Board column (after the prefix + underscore) to the
# corresponding field on the Board RFID Settings child table.
_RFID_FIELD_MAP: dict[str, str] = {
    "facility_code_start_position": "facility_code_start_position",
    "facility_code_length": "facility_code_length",
    "employee_id_start_position": "employee_id_start_position",
    "employee_id_length": "employee_id_length",
    "bit_size": "bit_size",
    "has_bit_reverse_feature": "bit_reverse_feature",
    "target_number_base_description": "target_number_base",
}


def _unpack_rfid_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract RFID setting rows from a flat Board API response.

    Each prefix in ``_RFID_PREFIXES`` maps to one child-table row.
    Rows where every numeric field is null/zero are skipped.
    """
    rows: list[dict[str, Any]] = []
    for prefix in _RFID_PREFIXES:
        row: dict[str, Any] = {}
        has_data = False
        for board_suffix, child_field in _RFID_FIELD_MAP.items():
            key = f"{prefix}_{board_suffix}"
            value = data.get(key)
            row[child_field] = value
            if value not in (None, "", 0, "0"):
                has_data = True
        if has_data:
            rows.append(row)
    return rows


def _extract_record(response: Any) -> dict[str, Any] | None:
    """Pull the first data record from a standard iCorp API response."""
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return data[0] if data else None
    return None


def _fetch_hardware_config(machine_name: str) -> dict[str, Any] | None:
    """Get the effective hardware configuration for a machine by name."""
    endpoint = (
        f"SV/MachineHardwareConfiguration/GetEffectiveConfiguration"
        f"?machineName={machine_name}"
    )
    return _extract_record(icorp_api_get(endpoint))


def _fetch_machine(machine_id: int | str) -> dict[str, Any] | None:
    """Get a machine record by its iCorp ID."""
    return _extract_record(icorp_api_get(f"SV/Machine/GetById?Id={machine_id}"))


def _fetch_board(board_id: int | str) -> dict[str, Any] | None:
    """Get a board record by its iCorp ID."""
    return _extract_record(icorp_api_get(f"SV/Board/GetById?Id={board_id}"))


def fetch_machine_hardware(machine_name: str, client_id: str) -> dict[str, Any] | None:
    """Look up a machine's hardware data via iCorp API endpoints.

    Returns a dict with ``serial_number``, ``prose_number``, ``mac_address``,
    and ``rfid_settings`` (a list of child-table row dicts), or ``None`` if
    the machine is not found or the API calls fail.
    """
    try:
        hw_config = _fetch_hardware_config(machine_name)
        if not hw_config:
            frappe.logger(_LOG).warning(
                f"No hardware configuration found for machine {machine_name!r}"
            )
            return None

        board_id = hw_config.get("board_id")
        machine_id = hw_config.get("machine_id")

        result: dict[str, Any] = {
            "serial_number": None,
            "prose_number": hw_config.get("board_serial_number"),
            "mac_address": None,
            "rfid_settings": [],
        }

        if machine_id:
            machine = _fetch_machine(machine_id)
            if machine:
                result["serial_number"] = machine.get("serial_number")

        if board_id:
            board = _fetch_board(board_id)
            if board:
                result["mac_address"] = board.get("mac_address")
                result["rfid_settings"] = _unpack_rfid_rows(board)

        return result

    except Exception:
        frappe.logger(_LOG).error(
            f"iCorp API error looking up machine {machine_name!r} "
            f"(client {client_id}): {frappe.get_traceback()}"
        )
        return None


def apply_machine_hardware(wr: "frappe._dict", data: dict[str, Any]) -> None:
    """Set hardware fields on a Warehouse Request doc from iCorp data."""
    for field in ("serial_number", "prose_number", "mac_address"):
        value = data.get(field)
        if value:
            setattr(wr, field, value)

    for rfid_row in data.get("rfid_settings") or []:
        wr.append("rfid_settings", rfid_row)
