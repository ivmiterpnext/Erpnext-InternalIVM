# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype


class MachineLockerConfiguration(BaseVirtualDoctype):
	KEY_FIELD = "id"
	BOOL_FIELDS = ["is_3d_printed", "enable_open_door_buzzer", "is_update_firmware"]
	SORT_FIELD_MAP = { "name": KEY_FIELD }

	endpoint = "SV/MachineLockerConfiguration"
