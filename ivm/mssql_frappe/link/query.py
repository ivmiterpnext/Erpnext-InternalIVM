import frappe
from frappe import _
from ivm.mssql_frappe.doctype.board_manufacturer.board_manufacturer import BoardManufacturer
from ivm.mssql_frappe.doctype.board_type.board_type import BoardType
from ivm.mssql_frappe.doctype.hardware_availability_type.hardware_availability_type import HardwareAvailabilityType

@frappe.whitelist()
def get_board_manufacturer_link(doctype, txt, searchfield, start, page_len, filters):
	try:
		# You can pre-load cached data or fetch live if needed
		items = BoardManufacturer.get_list()
		matches = []
		for item in items:
			# Perform basic filtering
			if txt.lower() in str(item.get("manufacturer_name", "")).lower():
				matches.append((item["name"], item["manufacturer_name"]))
		
		# Paginate manually
		return matches[start:start+page_len]
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_board_manufacturer_link error")
		return []

@frappe.whitelist()
def get_board_type_link(doctype, txt, searchfield, start, page_len, filters):
	try:
		items = BoardType.get_list()
		matches = []
		for item in items:
			# Perform basic filtering (assuming 'type_name' is the display field, adjust if needed)
			if txt.lower() in str(item.get("description", "")).lower():
				matches.append((item["name"], item["description"]))
		# Paginate manually
		return matches[start:start+page_len]
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_board_type_link error")
		return []

@frappe.whitelist()
def get_hardware_availability_type_link(doctype, txt, searchfield, start, page_len, filters):
	try:
		items = HardwareAvailabilityType.get_list()
		matches = []
		for item in items:
			# Perform basic filtering (assuming 'description' is the display field, adjust if needed)
			if txt.lower() in str(item.get("description", "")).lower():
				matches.append((item["code"], item["description"]))
		# Paginate manually
		return matches[start:start+page_len]
	except Exception:
		frappe.log_error(frappe.get_traceback(), "get_hardware_availability_type_link error")
		return []