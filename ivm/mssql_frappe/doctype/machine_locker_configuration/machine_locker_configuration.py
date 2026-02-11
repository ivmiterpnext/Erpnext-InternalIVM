# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.mssql_frappe.mssql_frappe.doctype.base_virtual_doctype import BaseVirtualDoctype


class MachineLockerConfiguration(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = ["is_3d_printed", "enable_open_door_buzzer", "is_update_firmware"]
	FIELD_MAP = { "name": "id" }
	endpoint = "SV/MachineLockerConfiguration"
