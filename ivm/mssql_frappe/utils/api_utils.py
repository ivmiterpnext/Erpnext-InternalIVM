import hashlib
import os
import requests
import frappe
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from ivm.mssql_frappe.utils.case_utils import dict_keys_to_snake_case, dict_keys_to_camel_case
from ivm.mssql_frappe.utils.filter_utils import filters_to_query_params


ICORP_API_BASE_URL = "https://dev.icorpapi.ivminc.com"
HEADWIND_API_BASE_URL = "https://iot.ivmapi.com/rest"
KEY_VAULT_URL = "https://ivm-apps-dev-kv-01.vault.azure.net//"
TENANT_ID = "5464da95-5a54-4466-8dde-04bd9e7f49da"
API_SCOPE = "api://74c6b7f8-98fe-4907-8fac-93ebc38fc521/.default"

def get_config_value(key, default=None):
    return frappe.conf.get(key.lower()) or os.environ.get(key.upper()) or default

def get_secret_client():
    try:
        print(KEY_VAULT_URL)
        vault_url = KEY_VAULT_URL
        credential = DefaultAzureCredential()
        return SecretClient(vault_url=vault_url, credential=credential)
    except Exception as e:
        print(e)

# ICorp
def get_icorp_auth():
    client = get_secret_client()
    print("Client: ", client)
    token_credential = ClientSecretCredential(
        tenant_id = TENANT_ID,
        client_id = client.get_secret("ICorpAPI-AzureAd-ClientId").value,
        client_secret = client.get_secret("ICorpAPI-AzureAd-ClientSecret").value
    )

    access_token = token_credential.get_token(API_SCOPE).token
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    return ICORP_API_BASE_URL, headers

def icorp_api_get(endpoint):
    base_url, headers = get_icorp_auth()
    response = requests.get(f"{base_url}/{endpoint}", headers=headers, timeout=60)
    print(response.json())
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        error_msg = _extract_error_message(response)
        frappe.throw(f"ICorp API Error: {error_msg or str(e)}")

    return dict_keys_to_snake_case(response.json())

def icorp_api_post(endpoint, data, headers=None):
    base_url, headers = get_icorp_auth()

    data = dict_keys_to_camel_case(data)
    data = _remove_empty_fields(data)
    if "created_by" not in data or not data["created_by"]:
        try:
            data["created_by"] = frappe.session.user
        except Exception:
            data["created_by"] = "system-frappe"

    url = f"{base_url}/{endpoint}"
    print("Data: ", data)
    response = requests.post(url, json=data, headers=headers, timeout=60)
    print(response.json())
    try:
        return response.json()
    except ValueError:
        frappe.log_error(f"Non-JSON response from {url}: {response.text}", "ICorp API POST Error")
        return {"error": "Invalid JSON response", "status_code": response.status_code, "text": response.text}

def icorp_api_put(endpoint, data):
    base_url, headers = get_icorp_auth()

    data = dict_keys_to_camel_case(data)
    data = _remove_empty_fields(data)
    if "modified_by" not in data or not data["modified_by"]:
        try:
            data["modified_by"] = frappe.session.user
        except Exception:
            data["modified_by"] = "system-frappe"

    url = f"{base_url}/{endpoint}"
    response = requests.put(url, json=data, headers=headers, timeout=60)

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        error_msg = _extract_error_message(response)
        frappe.throw(f"ICorp API Error: {error_msg or str(e)}")

    return response.json()

def icorp_api_delete(endpoint, data=None):
    base_url, headers = get_icorp_auth()
    url = f"{base_url}/{endpoint}"

    if data:
        data = dict_keys_to_camel_case(data)
        data = _remove_empty_fields(data)
        response = requests.delete(url, json=data, headers=headers, timeout=60)
    else:
        response = requests.delete(url, headers=headers, timeout=60)

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        error_msg = _extract_error_message(response)
        frappe.throw(f"ICorp API Error: {error_msg or str(e)}")

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
    try:
        client = get_secret_client()
        login = client.get_secret("Headwind-Privileged-Api-User").value
        password = client.get_secret("Headwind-Privileged-Api-User-Password").value
        password_md5 = hashlib.md5(password.encode('utf-8')).hexdigest().upper()
        payload = {"login": login, "password": password_md5}

        response = requests.post(f"{HEADWIND_API_BASE_URL}/public/jwt/login", json=payload, timeout=60)
        response.raise_for_status()
        return response.json()["id_token"]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_fetch_headwind_token error")
        return None

def get_headwind_auth(token=None):
    headers = {
        "Authorization": f"Bearer {token}" if token else "",
        "Accept": "application/json"
    }
    return HEADWIND_API_BASE_URL, headers

def headwind_api_request(method, endpoint, data=None, params=None):
    try:
        token = _fetch_headwind_token()
        base_url, headers = get_headwind_auth(token)

        if data:
            data = dict_keys_to_camel_case(data)

        response = requests.request(method, f"{base_url}/{endpoint}", headers=headers, json=data, params=params, timeout=60)

        if response.status_code == 401:
            token = _fetch_headwind_token()
            base_url, headers = get_headwind_auth(token)
            response = requests.request(method, f"{base_url}/{endpoint}", headers=headers, json=data, params=params, timeout=60)

        response.raise_for_status()
        return dict_keys_to_snake_case(response.json())
    except Exception:
        frappe.log_error(frappe.get_traceback(), "headwind_api_request error")
        return None

# Helpers
def _extract_error_message(response):
    try:
        error_json = response.json()
        return error_json.get("message") or str(error_json)
    except Exception:
        return response.text

def _remove_empty_fields(data):
    return {k: v for k, v in data.items() if v not in (None, "", [])}
