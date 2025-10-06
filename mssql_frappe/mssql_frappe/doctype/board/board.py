# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import icorp_api_get, icorp_api_post, icorp_get_count
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.data_utils import build_sort_params, set_attrs_from_dict, to_iso8601
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache_by_prefix


class Board(Document):
	_total_count = None

	KEY_FIELD = "id"
	BOOL_FIELDS = [
		"is_update_firmware", "is_update_connection", "is_update_rfid", "is_dhcp",
		"offline_vend_storage", "is_update_machine_motor_info",
		"is_pin_entry_enabled", "keypad_id_entry", "has_rfid_configuration",
		"primary_has_bit_reverse_feature", "secondary_has_bit_reverse_feature",
		"setting3_has_bit_reverse_feature", "setting4_has_bit_reverse_feature",
		"setting5_has_bit_reverse_feature"
	]
	SORT_FIELD_MAP = { "name": "id" }

	def check_if_latest(self):
		pass  # Disable optimistic locking for virtual DocType

	def validate_set_only_once(self):
		pass # Disable "Set Only Once" validation for virtual DocType

	@property
	def _action(self):
		# Always return "save" if not set
		return getattr(self, "__action", "save")

	def db_insert(self, *args, **kwargs):
		try:
			data = self.get_valid_dict()
			data = convert_fields_to_bool(data, self.BOOL_FIELDS)
			data["effective_date"] = to_iso8601(data["effective_date"])

			endpoint = "SV/Board"
			response = icorp_api_post(endpoint, data)
			data = response.get("data")

			if not data or "id" not in data:
				frappe.throw(f"Failed to create Board in external API: {response}")

			self.name = str(data["id"])
			for k, v in data.items():
				setattr(self, k, v)

			self.clear_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.db_insert error")
			raise

	def load_from_db(self):
		try:
			endpoint = f"SV/Board/GetById?Id={self.name}"
			response = icorp_api_get(endpoint)
			data = response.get("data", {})

			set_attrs_from_dict(self, data)
			self._set_vendnovation_configurations()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.load_from_db error")
			raise

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

			# Automatically sort configurations by effective_date descending
			configs = sorted(
				data,
				key=lambda c: c.get("effective_date") or "",
				reverse=True
			)

			for config in configs:
				self.append("vendnovation_configurations", config)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board._set_vendnovation_configurations error")

	def db_update(self, *args, **kwargs):
		# Board insert and update are the same api endpoint
		self.db_insert(*args, **kwargs)

	def delete(self):
		# Cannot currently delete Boards via API
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		filter_query = filters_to_query_params(filters)
		sort_query = build_sort_params(order_by, sort_field_map=Board.SORT_FIELD_MAP) if order_by else []

		cache_key = f"board_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		try:
			endpoint = f"SV/Board?page={page}&pageSize={page_length}"
			if filter_query:
				endpoint += f"&{filter_query}"
			if sort_query:
				for k, v in sort_query:
					endpoint += f"&{k}={v}"

			response = icorp_api_get(endpoint)
			data = response.get("data", [])
			pagination = response.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				Board._total_count = total_records

			items = api_data_to_frappe_dict(
				data,
				key_field=Board.KEY_FIELD,
			)

			frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
			return items
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		if Board._total_count is not None:
			return Board._total_count
		try:
			return icorp_get_count("SV/Board", filters)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	@staticmethod
	def clear_cache():
		Board._total_count = None
		clear_cache_by_prefix("board_list_cache")

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
        # Check for HTTP 404 error
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
