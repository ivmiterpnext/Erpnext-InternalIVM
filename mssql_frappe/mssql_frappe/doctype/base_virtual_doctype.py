import frappe
from frappe.model.document import Document
from mssql_frappe.utils.cache_util import LIST_CACHE_EXPIRES, clear_cache
from mssql_frappe.utils.case_utils import api_data_to_frappe_dict, convert_fields_to_bool
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.data_utils import build_sort_params, ensure_meta_is_ready, set_attrs_from_dict
from mssql_frappe.utils.api_utils import icorp_api_get, icorp_api_post

class BaseVirtualDoctype(Document):
    BOOL_FIELDS = []

    def db_insert(self, *args, **kwargs):
        try:
            data = self.get_valid_dict()
            data = convert_fields_to_bool(data, self.BOOL_FIELDS)
            data = self.pre_insert_data(data)
            endpoint = getattr(self, "endpoint", None) or f"SV/{self.__class__.__name__}"

            response = icorp_api_post(endpoint, data) or {}
            payload = response.get("data") or {}
            self.post_insert_response(payload)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.db_insert error")
            raise

    def pre_insert_data(self, data):
        return data

    def post_insert_response(self, payload):
        if hasattr(self, "KEY_FIELD") and self.KEY_FIELD in payload:
            self.name = str(payload[self.KEY_FIELD])

        for k, v in payload.items():
            setattr(self, k, v)

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

        endpoint = cls.get_list_endpoint(page, page_length, filter_query, sort_query)
        try:
            response = cls.get_list_from_api(endpoint, args)
            data = cls.extract_list_data(response)
            items = cls.process_list_data(data, args)

            frappe.cache().set_value(cache_key, items, expires_in_sec=LIST_CACHE_EXPIRES)
            return items
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{cls.__name__}.get_list error")
            return []

    @classmethod
    def preprocess_filters(cls, filters):
        return filters

    @classmethod
    def get_list_endpoint(cls, page, page_length, filter_query, sort_query):
        # Use endpoint if defined, else default logic
        if hasattr(cls, "endpoint") and cls.endpoint:
            endpoint = cls.endpoint
            params = []
            if filter_query:
                params.append(filter_query)
            if sort_query:
                for k, v in sort_query:
                    params.append(f"{k}={v}")
            if params:
                endpoint += "?" + "&".join(params)
            return endpoint
        else:
            endpoint = f"SV/{cls.__name__}?page={page}&pageSize={page_length}"
            if filter_query:
                endpoint += f"&{filter_query}"
            if sort_query:
                for k, v in sort_query:
                    endpoint += f"&{k}={v}"
            return endpoint

    @classmethod
    def get_list_from_api(cls, endpoint, args):
        # Subclasses can override for custom API calls
        return icorp_api_get(endpoint)

    @classmethod
    def extract_list_data(cls, response):
        # Subclasses can override for custom data extraction
        return response.get("data", [])

    @classmethod
    def process_list_data(cls, data, args):
        # Subclasses can override for custom post-processing
        return api_data_to_frappe_dict(data, getattr(cls, "KEY_FIELD", "id"))

    def load_from_db(self):
        if self.name and self.name.startswith("new-"):
            return
        try:
            ensure_meta_is_ready(self)
            endpoint = f"{self.endpoint}/GetById?Id={self.name}" if hasattr(self, "endpoint") and self.endpoint else f"SV/{self.__class__.__name__}/GetById?Id={self.name}"
            response = icorp_api_get(endpoint)
            data = response.get("data", {})
            self.post_process_loaded_data(data)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{self.__class__.__name__}.load_from_db error")
            raise

    def post_process_loaded_data(self, data):
        set_attrs_from_dict(self, data)

    def db_update(self):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    @classmethod
    def get_count(cls, args):
        filter_query = filters_to_query_params(args.get("filters"))
        count_key = f"{cls.__name__.lower()}_count_{filter_query}"

        cached_total = frappe.cache().get_value(count_key)
        # if cached_total is not None:
        #     return cached_total

        try:
            count = cls.get_count_from_api(args.get("filters"))
            frappe.cache().set_value(count_key, int(count), expires_in_sec=LIST_CACHE_EXPIRES)
            return count
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"{cls.__name__}.get_count error")
            return 0

    @classmethod
    def get_count_from_api(cls, filters):
        raise NotImplementedError("Subclasses must override get_count_from_api to fetch count from external API.")
