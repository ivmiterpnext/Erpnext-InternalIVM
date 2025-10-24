from datetime import datetime, timezone
import frappe
from frappe.model.document import Document
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.api_utils import icorp_api_get, icorp_api_post, icorp_api_put, icorp_api_delete, icorp_get_count

class BaseVirtualDoctype(Document):
    BOOL_FIELDS = []

# Get List
    @classmethod
    def get_list(cls, args):
        order_by = args.get("order_by")
        page_length = int(args.get("page_length") or 20)
        page = int(args.get("start") or 0) // page_length + 1

        filters = cls.preprocess_filters(args.get("filters"))
        filter_query = filters_to_query_params(filters)
        sort_query = build_sort_params(order_by, getattr(cls, "SORT_FIELD_MAP", {})) if order_by else []

        cache_key = f"{cls.__name__.lower()}_list_cache_{page}_{page_length}_{filter_query}_{sort_query}"
        cached = frappe.cache().get_value(cache_key)
        # if cached:
        #     return cached

        endpoint = cls.construct_list_endpoint(page, page_length, filter_query, sort_query)
        try:
            response = cls.get_list_via_api(endpoint, args)
            data = cls.extract_list_data(response)
            items = cls.process_list_data(data, args)

            frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
            return items
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{cls.__name__}.get_list error")
            return []

    @classmethod
    def preprocess_filters(cls, filters):
        """Hook to preprocess filters before constructing filter query for list API calls."""
        return filters

    @classmethod
    def construct_list_endpoint(cls, page, page_length, filter_query, sort_query):
        if not hasattr(cls, "endpoint") or not cls.endpoint:
            raise ValueError(f"Endpoint must be set in {cls.__name__} for list API calls.")
        params = [f"page={page}", f"pageSize={page_length}"]

        if filter_query:
            params.append(filter_query)

        if sort_query:
            for k, v in sort_query:
                params.append(f"{k}={v}")

        url = cls.endpoint
        if params:
            url += "?" + "&".join(params)
        return url

    @classmethod
    def get_list_via_api(cls, endpoint, args):
        # Subclasses can override for custom API calls
        return icorp_api_get(endpoint)

    @classmethod
    def extract_list_data(cls, response):
        # Subclasses can override for custom data extraction
        return response.get("data", [])

    @classmethod
    def process_list_data(cls, data, args):
        # Subclasses can override for custom post-processing
        print("process list data:", data)
        return api_data_to_frappe_dict(data, getattr(cls, "KEY_FIELD", "id"))

# Load from DB
    def load_from_db(self):
        if self.name and self.name.startswith("new-"):
            return

        try:
            ensure_meta_is_ready(self)
            endpoint = f"{self.endpoint}/GetById?Id={self.name}"
            response = self.fetch_via_api(endpoint)
            data = response.get("data", {})
            self.process_load_response(data)

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.load_from_db error")
            raise

    def fetch_via_api(self, endpoint):
        """Hook to allow subclasses to override the API used for loading a document."""
        return icorp_api_get(endpoint)

    def process_load_response(self, data):
        """Hook to preprocess load response before setting attributes."""
        set_attrs_from_dict(self, data)

# Insert
    def db_insert(self, *args, **kwargs):
        try:
            data = self.get_valid_dict()
            data = convert_fields_to_bool(data, self.BOOL_FIELDS)
            data["created_by"] = frappe.session.user if hasattr(frappe, "session") else "system-frappe"
            data["created_date"] = datetime.now(timezone.utc).isoformat()

            data = self.prepare_insert_data(data)

            response = self.insert_via_api(self.endpoint, data) or {}
            result = response.get("data") or {}

            if hasattr(self, "KEY_FIELD") and self.KEY_FIELD in result:
                self.name = str(result[self.KEY_FIELD])
            self.process_insert_response(result)
            for k, v in result.items():
                setattr(self, k, v)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.db_insert error")
            raise

    def prepare_insert_data(self, data):
        """Hook to preprocess insert data before API call."""
        return data

    def insert_via_api(self, endpoint, data):
        """Hook to allow subclasses to override the API used for insert."""
        return icorp_api_post(endpoint, data)

    def process_insert_response(self, result):
        """Hook to preprocess insert response before setting attributes."""
        pass

# Update
    def db_update(self):
        try:
            data = self.get_valid_dict()
            data = convert_fields_to_bool(data, self.BOOL_FIELDS)
            data[self.KEY_FIELD] = str(self.name)
            data["modified_by"] = frappe.session.user if hasattr(frappe, "session") else "system-frappe"
            data["modified_date"] = datetime.now(timezone.utc).isoformat()

            data = self.prepare_update_data(data)

            response = self.update_via_api(self.endpoint, data) or {}
            result = response.get("data") or {}

            if not result or self.KEY_FIELD not in result:
                frappe.throw(f"Failed to update {self.__class__.__name__} in external API: {response}")

            self.process_update_response(result)
            self.name = str(result[self.KEY_FIELD])
            for k, v in result.items():
                setattr(self, k, v)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.db_update error")
            raise

    def prepare_update_data(self, data):
        """Hook to preprocess update data before API call."""
        return data

    def update_via_api(self, endpoint, data):
        """Hook to allow subclasses to override the API used for update."""
        return icorp_api_put(endpoint, data)

    def process_update_response(self, result):
        """Hook to preprocess update response before setting attributes."""
        pass

# Delete
    def delete(self):
        try:
            if not hasattr(self, "endpoint") or not self.endpoint:
                raise NotImplementedError("Endpoint must be set for delete operation.")

            endpoint = f"{self.endpoint}?Id={self.name}"
            return self.delete_via_api(endpoint)

        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.delete error")
            raise

    def delete_via_api(self, endpoint):
        """Hook to allow subclasses to override the API used for delete."""
        return icorp_api_delete(endpoint)

# Count
    @classmethod
    def get_count(cls, args):
        filter_query = filters_to_query_params(args.get("filters"))
        count_key = f"{cls.__name__.lower()}_count_{filter_query}"

        cached_total = frappe.cache().get_value(count_key)
        # if cached_total is not None:
        #     return cached_total

        try:
            count = cls.get_count_via_api(args.get("filters"))
            frappe.cache().set_value(count_key, int(count), expires_in_sec=LIST_CACHE_EXPIRES)
            return count
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{cls.__name__}.get_count error")
            return 0

    @classmethod
    def get_count_via_api(cls, filters):
        """Hook to allow subclasses to override the API used for fetching total record count."""
        return icorp_get_count(cls.endpoint, filters)

# Hacks to make Frappe happy
    def check_if_latest(self):
        pass

    def validate_set_only_once(self):
        pass

    @property
    def _action(self):
        return getattr(self, "__action", "save")

    @staticmethod
    def get_stats(args):
        pass
