# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from mssql_frappe.utils.azure_api_utils import azure_api_get
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, api_items_to_frappe_dict
from mssql_frappe.utils.filter_utils import match_filter


class BoardManufacturer(Document):
    _api_data_cache = None

    def db_insert(self, *args, **kwargs):
        raise NotImplementedError

    def load_from_db(self):
        try:
            url = f"https://dev.icorpapi.ivminc.com/SV/BoardManufacturer/GetById?Id={self.name}"
            data = azure_api_get(url)
            item = dict_keys_to_snake_case(data.get("data", {}))
            # Save original API name value
            original_api_name = item.get('name')
            if 'id' in item:
                item['name'] = str(item['id'])
            if original_api_name is not None:
                item['manufacturer_name'] = original_api_name
            for k, v in item.items():
                if not isinstance(v, (str, int, float, bool, type(None))):
                    v = str(v)
                setattr(self, k, v)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "BoardManufacturer.load_from_db error")
            raise

    def db_update(self):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    @staticmethod
    def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
        try:
            url = "https://dev.icorpapi.ivminc.com/SV/BoardManufacturer"
            data = azure_api_get(url)
            items = []
            for item in data.get("data", []):
                item = dict_keys_to_snake_case(item)
                # Save the original manufacturer name
                if "name" in item:
                    item["manufacturer_name"] = item["name"]
                items.append(item)
            return api_items_to_frappe_dict(items, name_field="id")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "BoardManufacturer.get_list error")
            return []
    
    @staticmethod
    def get_count(filters=None, **kwargs):
        try:
            if BoardManufacturer._api_data_cache is not None:
                items = BoardManufacturer._api_data_cache
            else:
                url = "https://dev.icorpapi.ivminc.com/SV/BoardManufacturer"
                data = azure_api_get(url)
                items = data.get("data", [])
                BoardManufacturer._api_data_cache = items
            return len(items)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "BoardManufacturer.get_count error")
            return 0

    @staticmethod
    def get_stats(**kwargs):
        pass

    @staticmethod
    def clear_api_cache():
        BoardManufacturer._api_data_cache = None


@frappe.whitelist()
def get_board_manufacturer_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
    return BoardManufacturer.get_list(filters, page_length, start, order_by, **kwargs)

@frappe.whitelist()
def get_by_board_serial_number(board_serial_number):
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