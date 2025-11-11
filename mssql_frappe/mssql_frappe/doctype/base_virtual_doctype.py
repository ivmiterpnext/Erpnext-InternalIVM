from datetime import datetime, timezone
from urllib.parse import urlencode
import frappe
from frappe.model.document import Document
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.filter_utils import frappe_filters_to_dict, frappe_sort_to_dict
from mssql_frappe.utils.data_utils import ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.api_utils import headwind_api_request, icorp_api_get, icorp_api_post, icorp_api_put, icorp_api_delete


class BaseVirtualDoctype(Document):
    API_TYPE = None  # Must be set to "icorp", "headwind", etc. in each subclass
    BOOL_FIELDS = [] # List of boolean fields in the doctype for conversion
    FIELD_MAP = {}  # Mapping of Frappe field names to API field names. Frappe expects "name" for the primary key
    SORT_FIELD_MAP = {}  # Mapping of sortable fields if different from FIELD_MAP

# Get List
    @classmethod
    def get_list(cls, args):
        if not hasattr(cls, "API_TYPE") or cls.API_TYPE not in ("icorp", "headwind"):
            raise ValueError(f"API_TYPE must be set on {cls.__name__}.")
        if not hasattr(cls, "endpoint") or not cls.endpoint:
            raise ValueError(f"Endpoint must be set on {cls.__name__}.")

        params = cls.build_list_api_params(args)

        cache_key = f"{cls.__name__.lower()}_list_cache_{str(sorted(params.items()))}"
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached

        try:
            response = cls.get_list_via_api(cls.endpoint, params)
            response_data = cls.extract_data(response)
            result = cls.process_list_response(response_data, args)

            frappe.cache().set_value(cache_key, result, expires_in_sec=LIST_CACHE_EXPIRES)
            return result
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{cls.__name__}.get_list error")
            return []

    @classmethod
    def preprocess_filters(cls, filters):
        """Hook to preprocess filters before constructing filter query for list API calls."""
        return filters

    @classmethod
    def build_list_api_params(cls, args):
        page_length = int(args.get("page_length") or 20)
        start = int(args.get("start") or 0)
        page = (start // page_length) + 1

        filters = cls.preprocess_filters(args.get("filters"))
        params = frappe_filters_to_dict(filters, field_map=getattr(cls, "FIELD_MAP", {}))
        order_by = args.get("order_by")

        if order_by:
            params.update(frappe_sort_to_dict(order_by, field_map=getattr(cls, "FIELD_MAP", {})))

        params["page"] = page
        params["pageSize"] = page_length

        if cls.API_TYPE == "headwind":
            params["pageNum"] = params.pop("page")
            return params

        if cls.API_TYPE == "icorp":
            if "sortField" in params:
                params["sort[0].parameterName"] = params.pop("sortField", "")
                params["sort[0].sortOrder"] = params.pop("sortOrder", "")
            return params

        raise ValueError(f"Unknown API_TYPE '{cls.API_TYPE}' in {cls.__name__}.")

    @classmethod
    def get_list_via_api(cls, endpoint, params):
        if cls.API_TYPE == "headwind":
            return headwind_api_request("POST", endpoint, data=params)

        if cls.API_TYPE == "icorp":
            query_string = urlencode(params)
            endpoint_with_query = endpoint + "?" + query_string if query_string else endpoint
            return icorp_api_get(endpoint_with_query)

        raise ValueError(f"Unknown API_TYPE '{cls.API_TYPE}' in {cls.__name__}.")

    @classmethod
    def extract_data(cls, response):
        """Subclasses can override for custom data extraction"""
        return response.get("data", [])

    @classmethod
    def process_list_response(cls, data, args):
        """Subclasses can override for custom post-processing"""
        return api_data_to_frappe_dict(data, cls.FIELD_MAP.get("name"))

# Load from DB
    def load_from_db(self):
        if self.name and self.name.startswith("new-"):
            return
        if not hasattr(self, "API_TYPE"):
            raise ValueError(f"API_TYPE must be set on {self.__class__.__name__}.")

        try:
            ensure_meta_is_ready(self)
            endpoint = self.get_load_endpoint()

            response = self.fetch_via_api(endpoint)
            response_data = self.extract_data(response)
            result = self.process_load_response(response_data)

            set_attrs_from_dict(self, result)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.load_from_db error")
            raise

    def get_load_endpoint(self):
        """ Return the endpoint for loading a single record that subclasses can override.
            Defaults to ICorp, headwind must currently override. """
        return f"{self.endpoint}/GetById?Id={self.name}"

    def fetch_via_api(self, endpoint):
        if self.API_TYPE == "headwind":
            return headwind_api_request("GET", endpoint)

        if self.API_TYPE == "icorp":
            return icorp_api_get(endpoint)

        raise ValueError(f"Unknown API_TYPE '{self.API_TYPE}' in {self.__class__.__name__}.")

    def process_load_response(self, data):
        """Hook to preprocess load response before setting attributes."""
        return data

# Insert
    def db_insert(self, *args, **kwargs):
        if not hasattr(self, "API_TYPE"):
            raise NotImplementedError(f"API_TYPE must be set on {self.__class__.__name__}.")

        try:
            data = self.get_valid_dict()
            data = convert_fields_to_bool(data, self.BOOL_FIELDS)
            data["created_by"] = frappe.session.user if hasattr(frappe, "session") else "system-frappe"
            data["created_date"] = datetime.now(timezone.utc).isoformat()

            data = self.prepare_insert_data(data)
            endpoint = self.get_insert_endpoint()

            response = self.insert_via_api(endpoint, data)
            response_data = self.extract_data(response)

            key_field = self.FIELD_MAP.get("name")
            if key_field and key_field in response_data:
                self.name = str(response_data[key_field])

            result = self.process_insert_response(response_data)
            set_attrs_from_dict(self, result)

            clear_cache(self.__class__.__name__.lower())
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.db_insert error")
            raise

    def prepare_insert_data(self, data):
        """Hook to preprocess insert data before API call."""
        return data

    def get_insert_endpoint(self):
        """ Return the endpoint for inserting a record that subclasses can override.
            Defaults to ICorp, headwind must currently override. """
        return self.endpoint

    def insert_via_api(self, endpoint, data):
        if self.API_TYPE == "headwind":
            return headwind_api_request("POST", endpoint, data=data)

        if self.API_TYPE == "icorp":
            return icorp_api_post(endpoint, data)

        raise ValueError(f"Unknown API_TYPE '{self.API_TYPE}' in {self.__class__.__name__}.")

    def process_insert_response(self, data):
        """Hook to preprocess insert response before setting attributes."""
        return data

# Update
    def db_update(self, *args, **kwargs):
        if not hasattr(self, "API_TYPE"):
            raise ValueError(f"API_TYPE must be set on {self.__class__.__name__}.")
        if not hasattr(self, "endpoint") or not self.endpoint:
            raise ValueError(f"Endpoint must be set on {self.__class__.__name__}.")

        try:
            data = self.get_valid_dict()
            data = convert_fields_to_bool(data, self.BOOL_FIELDS)
            data["modified_by"] = frappe.session.user if hasattr(frappe, "session") else "system-frappe"
            data["modified_date"] = datetime.now(timezone.utc).isoformat()

            data = self.prepare_update_data(data)
            endpoint = self.get_update_endpoint()

            response = self.update_via_api(endpoint, data)
            response_data = self.extract_data(response)

            key_field = self.FIELD_MAP.get("name")
            if key_field and key_field in response_data:
                self.name = str(response_data[key_field])

            result = self.process_update_response(response_data)
            set_attrs_from_dict(self, result)

            clear_cache(self.__class__.__name__.lower())
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.db_update error")
            raise

    def prepare_update_data(self, data):
        """Hook to preprocess update data before API call."""
        return data

    def get_update_endpoint(self):
        """ Return the endpoint for updating a record that subclasses can override.
            Defaults to ICorp, headwind must currently override. """
        return self.endpoint

    def update_via_api(self, endpoint, data):
        """Hook to allow subclasses to override the API used for update."""
        return icorp_api_put(endpoint, data)

    def process_update_response(self, data):
        """Hook to preprocess update response before setting attributes."""
        self._set_modified_from_data(data)
        return data

# Delete
    def delete(self):
        if not hasattr(self, "API_TYPE"):
            raise ValueError(f"API_TYPE must be set on {self.__class__.__name__}.")
        if not hasattr(self, "endpoint") or not self.endpoint:
            raise ValueError(f"Endpoint must be set on {self.__class__.__name__}.")

        try:
            endpoint = self.get_delete_endpoint()

            response = self.delete_via_api(endpoint)
            response_data = self.extract_data(response)
            result = self.process_delete_response(response_data)

            clear_cache(self.__class__.__name__.lower())
            return result
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.delete error")
            raise

    def get_delete_endpoint(self):
        """Return the endpoint for deleting a record; subclasses can override. Defaults to ICorp, headwind must override."""
        return f"{self.endpoint}?Id={self.name}"

    def delete_via_api(self, endpoint):
        """Hook to allow subclasses to override the API used for delete."""
        if self.API_TYPE == "headwind":
            raise NotImplementedError("Delete not implemented for Headwind API in base class.")
        if self.API_TYPE == "icorp":
            return icorp_api_delete(endpoint)
        raise ValueError(f"Unknown API_TYPE '{self.API_TYPE}' in {self.__class__.__name__}.")

    def process_delete_response(self, data):
        """Hook to preprocess delete response before returning."""
        return data

# Count
    @classmethod
    def get_count(cls, args):
        if not hasattr(cls, "API_TYPE"):
            raise ValueError(f"API_TYPE must be set on {cls.__name__}.")
        if not hasattr(cls, "endpoint") or not cls.endpoint:
            raise ValueError(f"Endpoint must be set on {cls.__name__}.")

        params = cls.build_list_api_params(args)
        cache_key = f"{cls.__name__.lower()}_count_cache_{str(sorted(params.items()))}"
        cached = frappe.cache().get_value(cache_key)
        if cached is not None:
            return cached

        try:
            response = cls.get_count_via_api(cls.endpoint, params)
            count = cls.extract_count(response)

            frappe.cache().set_value(cache_key, int(count), expires_in_sec=LIST_CACHE_EXPIRES)
            return count
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{cls.__name__}.get_count error")
            return 0

    @classmethod
    def get_count_via_api(cls, endpoint, params):
        params["page"] = 1
        params["pageSize"] = 1

        if cls.API_TYPE == "headwind":
            return headwind_api_request("POST", endpoint, data=params)

        if cls.API_TYPE == "icorp":
            query_string = urlencode(params)
            endpoint_with_query = endpoint + "?" + query_string if query_string else endpoint
            return icorp_api_get(endpoint_with_query)

        raise ValueError(f"Unknown API_TYPE '{cls.API_TYPE}' in {cls.__name__}.")

    @classmethod
    def extract_count(cls, response):
        """Extract the count from the API response. Subclasses can override if needed."""
        pagination = response.get("pagination", {})
        total_records = pagination.get("total_records")
        return int(total_records) if total_records is not None else 0

# Helpers
    def _set_modified_from_data(self, data):
        for key in ("modified", "modified_date", "modifiedDate"):
            if key in data and data[key]:
                self.modified = data[key]
                return

        self.modified = frappe.utils.now()

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
