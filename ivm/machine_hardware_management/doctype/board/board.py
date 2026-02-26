# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from ivm.ivm.utils.base_virtual_doctype import BaseVirtualDoctype
from ivm.ivm.utils.api_utils import icorp_api_get
from ivm.ivm.utils.case_utils import api_data_to_frappe_dict
from ivm.ivm.utils.data_utils import set_attrs_from_dict, to_iso8601


class Board(BaseVirtualDoctype):
	API_TYPE = "icorp"
	BOOL_FIELDS = [
		"is_update_firmware", "is_update_connection", "is_update_rfid", "is_dhcp",
		"offline_vend_storage", "is_update_machine_motor_info",
		"is_pin_entry_enabled", "keypad_id_entry", "has_rfid_configuration",
		"primary_has_bit_reverse_feature", "secondary_has_bit_reverse_feature",
		"setting3_has_bit_reverse_feature", "setting4_has_bit_reverse_feature",
		"setting5_has_bit_reverse_feature"
	]
	FIELD_MAP = { "name": "id" }
	endpoint = "SV/Board"

# Get List Overrides
	@classmethod
	def preprocess_filters(cls, filters):
		new_filters = []
		for f in filters or []:
			if f[1] == "board_firmware_id":
				version = frappe.db.get_value("Board Firmware", f[3], "version")
				if version:
					new_filters.append([f[0], "firmware_version", f[2], version])
				else:
					continue
			else:
				new_filters.append(f)
		return new_filters

	@classmethod
	def process_list_response(cls, data, args):
		for row in data:
			if "board_manufacturer_name" in row:
				row["board_manufacturer_id"] = row["board_manufacturer_name"]
			if "hardware_availability_type_description" in row:
				row["hardware_availability_type_code"] = row["hardware_availability_type_description"]
			if "board_firmware_version" in row:
				row["board_firmware_id"] = row["board_firmware_version"]

		return api_data_to_frappe_dict(data, cls.FIELD_MAP.get("name"))

# Load from DB Overrides
	def process_load_response(self, data):
		self._set_vendnovation_configurations()
		set_attrs_from_dict(self, data)

# Insert Overrides
	def prepare_insert_data(self, data):
		data["effective_date"] = to_iso8601(data["effective_date"])
		return data

# Helpers
	def _set_vendnovation_configurations(self):
		try:
			endpoint = f"SV/BoardVendnovationConfiguration/GetEffectiveConfiguration?Id={self.name}"
			response = icorp_api_get(endpoint)
			data = response.get("data", {})

			set_attrs_from_dict(self, data)
			self.has_rfid_configuration = 1 if getattr(self, "board_rfid_configuration_id", None) not in (None, '', 'null') else 0

			endpoint = f"SV/BoardVendnovationConfiguration/GetByBoardSerialNumber?SerialNumber={self.serial_number}"
			response = icorp_api_get(endpoint)
			data = response.get("data", {})

			configs = sorted(
				data,
				key=lambda c: c.get("effective_date") or "",
				reverse=True
			)

			for config in configs:
				self.append("vendnovation_configurations", config)
		except Exception as e:
				frappe.log_error(f"{e}\n{frappe.get_traceback()}", "Board._set_vendnovation_configurations error")

	def db_update(self, *args, **kwargs):
		# Board insert and update are the same api endpoint
		self.db_insert(*args, **kwargs)

	def delete(self):
		# Cannot currently delete Boards via API
		raise NotImplementedError

# Select logic
@frappe.whitelist()
def get_rfid_target_number_base_types():
    endpoint = "SV/BoardRFIDTargetNumberBaseType"

    response = icorp_api_get(endpoint)
    items = response.get("data", [])

    options = [
        {
            "name": str(item.get("id")),
			"code": item.get("code"),
            "description": item.get("description")
        }
        for item in items
    ]
    return options

@frappe.whitelist()
def get_manufacturer_by_serial_number(board_serial_number):
    endpoint = f"SV/BoardManufacturer/GetByBoardSerialNumber?boardSerialNumber={board_serial_number}"
    try:
        data = icorp_api_get(endpoint)
        result = data.get("data", {})
        if result:
            return {
                "id": result.get("id"),
                "manufacturer_name": result.get("name")
            }
        return None
    except Exception as e:
        if hasattr(e, 'response') and getattr(e.response, 'status_code', None) == 404:
            return {
                "id": None,
                "manufacturer_name": "Invalid PROSE Number"
            }

        frappe.log_error(frappe.get_traceback(), "get_manufacturer_by_serial_number error")
        return {
            "id": None,
            "manufacturer_name": "Error"
        }
