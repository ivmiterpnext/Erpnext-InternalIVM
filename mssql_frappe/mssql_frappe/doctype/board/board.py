# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.azure_api_utils import azure_api_get, azure_api_post
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, api_items_to_frappe_dict
from mssql_frappe.utils.filter_utils import filters_to_query_params
import datetime

API_BASE_URL = "https://dev.icorpapi.ivminc.com"

_board_total_count = None

class Board(Document):
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

			# Convert/cast fields as needed for API
			for k in [
				"is_update_firmware", "is_update_connection", "is_update_rfid", "is_dhcp",
				"offline_vend_storage", "is_update_machine_motor_info",
				"is_pin_entry_enabled", "keypad_id_entry", "has_rfid_configuration",
				"primary_has_bit_reverse_feature", "secondary_has_bit_reverse_feature",
				"setting3_has_bit_reverse_feature", "setting4_has_bit_reverse_feature",
				"setting5_has_bit_reverse_feature"
			]:
				if k in data:
					if isinstance(data[k], str):
						data[k] = bool(int(data[k]))
					else:
						data[k] = bool(data[k])

			if data["effective_date"]:
				dt = datetime.datetime.fromisoformat(data["effective_date"])
				data["effective_date"] = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]

			url = f"{API_BASE_URL}/SV/Board"
			print("program_type before API:", data.get("program_type"))
			print("program_type_code before API:", data.get("program_type_code"))
			response = azure_api_post(url, data)
			board_data = response.get("data")

			if not board_data or "id" not in board_data:
				frappe.throw("Failed to create Board in external API: {}".format(response))

			self.name = str(board_data["id"])
			for k, v in board_data.items():
				setattr(self, k, v)

			self.clear_board_list_cache()
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.db_insert error")
			raise

	def load_from_db(self):
		try:
			url = f"{API_BASE_URL}/SV/Board/GetById?Id={self.name}"

			item = azure_api_get(url)
			board_data = item.get("data", {})

			# If board_data is a list, get the first item
			if isinstance(board_data, list):
				if not board_data:
					return  # No data found
				board_data = board_data[0]

			for k, v in board_data.items():
				# Set ids to string
				if k.endswith('id'):
					v = str(v) if v is not None else ''
				# Set None to empty string for all fields except numbers/bools
				elif v is None:
					v = ''
				# Convert complex types to string for frappe safety
				elif not isinstance(v, (str, int, float, bool)):
					v = str(v)
				setattr(self, k, v)

			# Merge BoardVendnovationConfiguration and Board Data
			try:
				board_id = getattr(self, "id", None)
				if board_id:
					url = f"{API_BASE_URL}/SV/BoardVendnovationConfiguration/GetEffectiveConfiguration?Id={board_id}"
					item = azure_api_get(url)
					item = item.get("data", {})
					print(item)
					for k, v in item.items():
						if k.endswith('id'):
							v = str(v) if v is not None else ''
						elif not isinstance(v, (str, int, float, bool, type(None))):
							v = str(v)
						setattr(self, k, v)

					if getattr(self, "board_rfid_configuration_id", None) not in (None, '', 'null'):
						self.has_rfid_configuration = 1
					else:
						self.has_rfid_configuration = 0

				serial_number = getattr(self, "serial_number", None)
				if serial_number:
					url = f"{API_BASE_URL}/SV/BoardVendnovationConfiguration/GetByBoardSerialNumber?SerialNumber={serial_number}"
					result = azure_api_get(url)
	
					configs = sorted(
						result.get("data", []),
						key=lambda c: c.get("effective_date") or "",
						reverse=True
					)

					self.vendnovation_configurations = []
					for config in configs:
						self.append("vendnovation_configurations", {
							"id": config.get("id"),
							"effective_date": config.get("effective_date"),
							"is_in_effect": config.get("is_in_effect"),
							"primary_connection": config.get("primary_board_connection_name"),
							"secondary_connection": config.get("secondary_board_connection_name"),
							"rfid_configuration_id": config.get("board_rfid_configuration_id"),
							"comments": config.get("comments")
						})

			except Exception:
				frappe.log_error(frappe.get_traceback(), "Board.load_from_db BoardVendnovationConfiguration list error")
			except Exception:
				frappe.log_error(frappe.get_traceback(), "Board.load_from_db BoardVendnovationConfiguration error")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.load_from_db error")
			raise

			
		

	def db_update(self, *args, **kwargs):
		# Board insert and update are the same api endpoint
		self.db_insert(*args, **kwargs)

	def delete(self):
		# Cannot currently delete Boards via API
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		global _board_total_count
		page = (start // page_length) + 1
		filter_query = filters_to_query_params(filters)
		cache_key = f"board_list_cache_{page}_{page_length}_{filter_query}"
		cached = frappe.cache().get_value(cache_key)
		if cached:
			return cached

		try:
			url = f"{API_BASE_URL}/SV/Board?page={page}&pageSize={page_length}"
			if filter_query:
				url += f"&{filter_query}"
			result = azure_api_get(url)

			items = result.get("data", [])
			pagination = result.get("pagination", {})
			total_records = pagination.get("total_records")

			if total_records is not None:
				_board_total_count = int(total_records)
			value = api_items_to_frappe_dict(items, name_field="id")
			frappe.cache().set_value(cache_key, value, expires_in_sec=300)
			return value
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		global _board_total_count
		if _board_total_count is not None:
			return _board_total_count
		try:
			url = f"{API_BASE_URL}/SV/Board?page=1&pageSize=1"
			result = azure_api_get(url)
			pagination = result.get("pagination", {})
			total_records = pagination.get("total_records")
			if total_records is not None:
				_board_total_count = int(total_records)
			return _board_total_count
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Board.get_count error")
			return 0

	@staticmethod
	def get_stats(**kwargs):
		pass

	@staticmethod
	def clear_board_list_cache():
		cache = frappe.cache()
		for key in cache.keys("board_list_cache_*"):
			cache.delete_key(key)

# Dropdown logic
@frappe.whitelist()
def get_board_types():
    url = f"{API_BASE_URL}/SV/BoardType"

    response = azure_api_get(url)
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
def get_rfid_target_number_base_types():
    url = f"{API_BASE_URL}/SV/BoardRFIDTargetNumberBaseType"

    response = azure_api_get(url)
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
def get_board_firmware_versions(board_manufacturer_id=None):
    url = f"{API_BASE_URL}/SV/BoardFirmware?pageSize=999&page=1"

    response = azure_api_get(url)
    items = response.get("data", [])

    if board_manufacturer_id:
        items = [item for item in items if str(item.get("board_manufacturer_id")) == str(board_manufacturer_id)]

    options = [
        {
            "name": str(item.get("id")),
            "version": item.get("version")
        }
        for item in items
    ]
    return options

@frappe.whitelist()
def get_board_connections():
    url = f"{API_BASE_URL}/SV/BoardConnection"

    response = azure_api_get(url)
    items = response.get("data", [])

    options = [
        {
            "name": str(item.get("id")),
            "connection_name": item.get("name")
        }
        for item in items
    ]
    return options

@frappe.whitelist()
def get_hardware_availability_types():
	url = f"{API_BASE_URL}/SV/HardwareAvailabilityType"

	response = azure_api_get(url)
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
    url = f"https://dev.icorpapi.ivminc.com/SV/BoardManufacturer/GetByBoardSerialNumber?boardSerialNumber={board_serial_number}"
    try:
        data = azure_api_get(url)
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
        frappe.log_error(frappe.get_traceback(), "get_by_board_serial_number error")
        return {
            "id": None,
            "manufacturer_name": "Error"
        }