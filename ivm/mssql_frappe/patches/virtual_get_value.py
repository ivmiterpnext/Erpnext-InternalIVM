import frappe
from frappe.desk.search import get_value as frappe_get_value
from mssql_frappe.mssql_frappe.doctype.board_manufacturer.board_manufacturer import BoardManufacturer
from mssql_frappe.mssql_frappe.doctype.board_type.board_type import BoardType
from mssql_frappe.mssql_frappe.doctype.hardware_availability_type.hardware_availability_type import HardwareAvailabilityType

@frappe.whitelist()
def virtual_get_value(doctype, name, fieldname, **kwargs):
    # Board Manufacturer
    if doctype == "Board Manufacturer":
        return BoardManufacturer.get_value(name, fieldname)
    # Board Type
    if doctype == "Board Type":
        return BoardType.get_value(name, fieldname)
    # Hardware Availability Type
    if doctype == "Hardware Availability Type":
        return HardwareAvailabilityType.get_value(name, fieldname)
    # fallback to original for all other doctypes
    return frappe_get_value(doctype, name, fieldname, **kwargs)
