# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from warnings import filters
import frappe
from frappe.model.document import Document
from mssql_frappe.utils.azure_api_utils import azure_api_get
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, api_items_to_frappe_dict

class HardwareAvailabilityType(Document):
    # Simple in-memory cache for the duration of the request
    _api_data_cache = None

    def db_insert(self, *args, **kwargs):
        raise NotImplementedError

    def load_from_db(self):
        try:
            url = f"https://dev.icorpapi.ivminc.com/SV/HardwareAvailabilityType/GetByCode?Code={self.name}"
            data = azure_api_get(url)
            item = dict_keys_to_snake_case(data.get("data", {}))
            for k, v in item.items():
                if not isinstance(v, (str, int, float, bool, type(None))):
                    v = str(v)
                setattr(self, k, v)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "HardwareAvailabilityType.load_from_db error")
            raise

    def db_update(self):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    @staticmethod
    def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
        try:
            url = "https://dev.icorpapi.ivminc.com/SV/HardwareAvailabilityType"
            data = azure_api_get(url)
            items = data.get("data", [])

            if kwargs.get("as_list"):
                return [(item["code"], item["description"], item["description"]) for item in items]
            return api_items_to_frappe_dict(items, name_field="code")

            # if filters:
            #     for flt in filters:
            #         result = [item for item in result if match_filter(item, flt)]
                    
            # result = apply_multi_field_sort(result, order_by)
            # return result
            
        except Exception:
            frappe.log_error(frappe.get_traceback(), "HardwareAvailabilityType.get_list error")
            return []

    @staticmethod
    def get_count(filters=None, **kwargs):
        try:
            if HardwareAvailabilityType._api_data_cache is not None:
                items = HardwareAvailabilityType._api_data_cache
            else:
                url = "https://dev.icorpapi.ivminc.com/SV/HardwareAvailabilityType"
                data = azure_api_get(url)
                items = data.get("data", [])
                HardwareAvailabilityType._api_data_cache = items
            return len(items)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "HardwareAvailabilityType.get_count error")
            return 0

    @staticmethod
    def get_stats(**kwargs):
        pass

    @staticmethod
    def clear_api_cache():
        HardwareAvailabilityType._api_data_cache = None

@frappe.whitelist()
def get_hardware_availability_type_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
    return HardwareAvailabilityType.get_list(filters, page_length, start, order_by, **kwargs)


@frappe.whitelist()
def run_hardware_availability_type_sync():
    sync_hardware_availability_types()
    return "Sync complete"


def sync_hardware_availability_types():
    items = get_hardware_availability_type_list()
    for item in items:
        # Try to get existing doc
        doc = frappe.get_all("Hardware Availability Type", filters={"name": item["code"]})
        if doc:
            # Update description if needed
            frappe.db.set_value("Hardware Availability Type", item["code"], "description", item["description"])
        else:
            # Create new doc
            new_doc = frappe.get_doc({
                "doctype": "Hardware Availability Type",
                "name": item["code"],
                "code": item["code"],
                "description": item["description"],
                "id": item["id"]
            })
            new_doc.insert(ignore_permissions=True)
    frappe.db.commit()