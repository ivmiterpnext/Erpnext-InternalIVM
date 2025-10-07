import hashlib
import os
import requests
import frappe
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, dict_keys_to_camel_case
from mssql_frappe.utils.filter_utils import filters_to_query_params

ICORP_API_BASE_URL = os.environ.get("ICORP_API_BASE_URL")
HEADWIND_API_BASE_URL = os.environ.get("HEADWIND_API_BASE_URL")
KEY_VAULT_URL = os.environ.get("AZURE_KEYVAULT_URL")
TENANT_ID = os.environ.get("AZURE_TENANT_ID")
API_SCOPE = os.environ.get("AZURE_API_SCOPE")

_credential = DefaultAzureCredential()
_client = SecretClient(vault_url=KEY_VAULT_URL, credential=_credential)
_headwind_token = None

# ICorp
def _get_icorp_headers():
    client_id = _client.get_secret("ICorpAPI-AzureAd-ClientId").value
    client_secret = _client.get_secret("ICorpAPI-AzureAd-ClientSecret").value

    token_credential = ClientSecretCredential(
        tenant_id=TENANT_ID,
        client_id=client_id,
        client_secret=client_secret
    )
    access_token = token_credential.get_token(API_SCOPE).token

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    return headers

def icorp_api_get(endpoint):
    try:
        headers = _get_icorp_headers()
        response = requests.get(f"{ICORP_API_BASE_URL}/{endpoint}", headers=headers, timeout=10)
        response.raise_for_status()
        return dict_keys_to_snake_case(response.json())
    except Exception:
        frappe.log_error(frappe.get_traceback(), "icorp_api_get error")

def icorp_api_post(endpoint, data):
    headers = _get_icorp_headers()

    if "created_by" not in data or not data["created_by"]:
        try:
            data["created_by"] = frappe.session.user
        except Exception:
            data["created_by"] = "system-frappe"

    data = dict_keys_to_camel_case(data)
    data = _remove_empty_fields(data)

    response = requests.post(f"{ICORP_API_BASE_URL}/{endpoint}", json=data, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()

def icorp_api_put(endpoint, data):
    headers = _get_icorp_headers()

    if "modified_by" not in data or not data["modified_by"]:
        try:
            data["modified_by"] = frappe.session.user
        except Exception:
            data["modified_by"] = "system-frappe"

    data = dict_keys_to_camel_case(data)
    data = _remove_empty_fields(data)

    response = requests.put(f"{ICORP_API_BASE_URL}/{endpoint}", json=data, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()

def icorp_api_delete(endpoint, data=None):
    headers = _get_icorp_headers()

    if data:
        data = dict_keys_to_camel_case(data)
        data = _remove_empty_fields(data)
        response = requests.delete(f"{ICORP_API_BASE_URL}/{endpoint}", json=data, headers=headers, timeout=10)
    else:
        response = requests.delete(f"{ICORP_API_BASE_URL}/{endpoint}", headers=headers, timeout=10)

    response.raise_for_status()
    if not response.text.strip():
        return {}
    return response.json()

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
    login = _client.get_secret("Headwind-Privileged-Api-User").value
    password = _client.get_secret("Headwind-Privileged-Api-User-Password").value
    password_md5 = hashlib.md5(password.encode('utf-8')).hexdigest().upper()
    payload = {"login": login, "password": password_md5}
    response = requests.post(f"{HEADWIND_API_BASE_URL}/public/jwt/login", json=payload, timeout=10)
    response.raise_for_status()
    return response.json()["id_token"]

def _get_headwind_headers():
    global _headwind_token

    if not _headwind_token:
        _headwind_token = _fetch_headwind_token()

    return {
        "Authorization": f"Bearer {_headwind_token}",
        "Accept": "application/json"
    }

def headwind_api_request(method, endpoint, data=None, params=None):
    global _headwind_token

    if data:
        data = dict_keys_to_camel_case(data)
    headers = _get_headwind_headers()
    response = requests.request(method, f"{HEADWIND_API_BASE_URL}/{endpoint}", headers=headers, json=data, params=params, timeout=10)

    if response.status_code == 401:
        _headwind_token = _fetch_headwind_token()
        headers = _get_headwind_headers()
        response = requests.request(method, f"{HEADWIND_API_BASE_URL}/{endpoint}", headers=headers, json=data, params=params, timeout=10)
    response.raise_for_status()
    return dict_keys_to_snake_case(response.json())

def _remove_empty_fields(data):
    return {k: v for k, v in data.items() if v not in (None, "", [])}
