import hashlib
import os
import requests
import frappe
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, dict_keys_to_camel_case
from mssql_frappe.utils.filter_utils import filters_to_query_params


def get_config_value(key, default=None):
    return frappe.conf.get(key.lower()) or os.environ.get(key.upper()) or default

def get_secret_client():
    vault_url = get_config_value("KEY_VAULT_URL")
    credential = DefaultAzureCredential()
    return SecretClient(vault_url=vault_url, credential=credential)

# ICorp
def get_icorp_auth():
    client = get_secret_client()
    client_id = client.get_secret("ICorpAPI-AzureAd-ClientId").value
    client_secret = client.get_secret("ICorpAPI-AzureAd-ClientSecret").value
    tenant_id = get_config_value("TENANT_ID")
    api_scope = get_config_value("API_SCOPE")
    base_url = get_config_value("ICORP_API_BASE_URL")

    token_credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    access_token = token_credential.get_token(api_scope).token

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    return base_url, headers

def icorp_api_get(endpoint):
    try:
        base_url, headers = get_icorp_auth()
        response = requests.get(f"{base_url}/{endpoint}", headers=headers, timeout=30)
        response.raise_for_status()
        return dict_keys_to_snake_case(response.json())
    except Exception:
        frappe.log_error(frappe.get_traceback(), "icorp_api_get error")

def icorp_api_post(endpoint, data):
    try:
        base_url, headers = get_icorp_auth()

        if "created_by" not in data or not data["created_by"]:
            try:
                data["created_by"] = frappe.session.user
            except Exception:
                data["created_by"] = "system-frappe"

        data = dict_keys_to_camel_case(data)
        data = _remove_empty_fields(data)

        response = requests.post(f"{base_url}/{endpoint}", json=data, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "icorp_api_post error")
        return None

def icorp_api_put(endpoint, data):
    try:
        base_url, headers = get_icorp_auth()

        if "modified_by" not in data or not data["modified_by"]:
            try:
                data["modified_by"] = frappe.session.user
            except Exception:
                data["modified_by"] = "system-frappe"

        data = dict_keys_to_camel_case(data)
        data = _remove_empty_fields(data)

        response = requests.put(f"{base_url}/{endpoint}", json=data, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "icorp_api_put error")
        return None

def icorp_api_delete(endpoint, data=None):
    try:
        base_url, headers = get_icorp_auth()

        if data:
            data = dict_keys_to_camel_case(data)
            data = _remove_empty_fields(data)
            response = requests.delete(f"{base_url}/{endpoint}", json=data, headers=headers, timeout=30)
        else:
            response = requests.delete(f"{base_url}/{endpoint}", headers=headers, timeout=30)

        response.raise_for_status()
        if not response.text.strip():
            return {}
        return response.json()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "icorp_api_delete error")
        return None

def icorp_get_count(endpoint, filters=None):
    try:
        url = f"{endpoint}?page=1&pageSize=1"
        filter_query = filters_to_query_params(filters)

        if filter_query:
            url += f"&{filter_query}"

        result = icorp_api_get(url)
        pagination = result.get("pagination", {})
        total_records = pagination.get("total_records")

        return int(total_records) if total_records is not None else 0
    except Exception:
        frappe.log_error(frappe.get_traceback(), "get_icorp_count error")
        return 0

# Headwind
def _fetch_headwind_token():
    try:
        client = get_secret_client()
        base_url = get_config_value("HEADWIND_API_BASE_URL")
        login = client.get_secret("Headwind-Privileged-Api-User").value
        password = client.get_secret("Headwind-Privileged-Api-User-Password").value
        password_md5 = hashlib.md5(password.encode('utf-8')).hexdigest().upper()
        payload = {"login": login, "password": password_md5}

        response = requests.post(f"{base_url}/public/jwt/login", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()["id_token"]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_fetch_headwind_token error")
        return None

def get_headwind_auth(token=None):
    base_url = get_config_value("HEADWIND_API_BASE_URL")
    headers = {
        "Authorization": f"Bearer {token}" if token else "",
        "Accept": "application/json"
    }
    return base_url, headers

def headwind_api_request(method, endpoint, data=None, params=None):
    try:
        token = _fetch_headwind_token()
        base_url, headers = get_headwind_auth(token)
        if data:
            data = dict_keys_to_camel_case(data)
        response = requests.request(method, f"{base_url}/{endpoint}", headers=headers, json=data, params=params, timeout=30)

        if response.status_code == 401:
            token = _fetch_headwind_token()
            base_url, headers = get_headwind_auth(token)
            response = requests.request(method, f"{base_url}/{endpoint}", headers=headers, json=data, params=params, timeout=30)
        response.raise_for_status()
        return dict_keys_to_snake_case(response.json())
    except Exception:
        frappe.log_error(frappe.get_traceback(), "headwind_api_request error")
        return None

def _remove_empty_fields(data):
    return {k: v for k, v in data.items() if v not in (None, "", [])}
