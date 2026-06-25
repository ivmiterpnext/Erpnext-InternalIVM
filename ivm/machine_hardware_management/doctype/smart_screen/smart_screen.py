# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.machine_hardware_management.utils.base_virtual_doctype import BaseVirtualDoctype
from ivm.integrations.headwind import headwind_api_request
from ivm.machine_hardware_management.utils.data_utils import set_attrs_from_dict


class SmartScreen(BaseVirtualDoctype):
    API_TYPE = "headwind"
    FIELD_MAP = {"name": "number"}
    endpoint = "private/devices/search"

    def db_insert(self, *args, **kwargs):
        raise NotImplementedError

    def db_update(self):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    @classmethod
    def extract_data(cls, response):
        # List endpoint
        if "devices" in response.get("data", {}):
            return response.get("data", {}).get("devices", {}).get("items", [])
        # Detail endpoint
        return response.get("data", {})

    @classmethod
    def extract_count(cls, response):
        return response.get("data", {}).get("devices", {}).get("total_items_count", 0)

    def get_load_endpoint(self):
        return f"private/devices/number/{self.name}"

    def fetch_via_api(self, endpoint):
        return headwind_api_request("GET", endpoint)

    def process_load_response(self, data):
        if data.get("id"):
            self.name = str(data["number"])

        if "groups" in data and isinstance(data["groups"], list):
            data["groups"] = [{"group_id": g["id"]} for g in data["groups"] if isinstance(g, dict) and "id" in g]
        else:
            data["groups"] = []

        child_table_map = {
            "groups": "group_id",
        }
        set_attrs_from_dict(self, data, child_table_map)

    def get_indicator(self):
        color = (self.status_code or "gray").lower()
        label = self.status_code.capitalize() if self.status_code else "Unknown"
        return (label, color, {"status_code": self.status_code})
