
import frappe
import hashlib
import os
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, dict_keys_to_camel_case, api_items_to_frappe_dict
import requests

ICORP_API_BASE_URL = "https://dev.icorpapi.ivminc.com" # os.environ.get("ICORP_API_BASE_URL")
HEADWIND_API_BASE_URL = "https://iot.ivmapi.com/rest" # os.environ.get("HEADWIND_API_BASE_URL")
KEY_VAULT_URL = "https://ivm-apps-dev-kv-01.vault.azure.net//" # os.environ.get("AZURE_KEYVAULT_URL")
TENANT_ID = "5464da95-5a54-4466-8dde-04bd9e7f49da" # os.environ.get("AZURE_TENANT_ID")
API_SCOPE = "api://74c6b7f8-98fe-4907-8fac-93ebc38fc521/.default" # os.environ.get("AZURE_API_SCOPE")

credential = DefaultAzureCredential()
client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)

# ICorp
def _get_icorp_headers():
    client_id = client.get_secret("ICorpAPI-AzureAd-ClientId").value
    client_secret = client.get_secret("ICorpAPI-AzureAd-ClientSecret").value

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
        response = requests.get(f"{ICORP_API_BASE_URL}/{endpoint}", headers=headers)
        response.raise_for_status()
        return dict_keys_to_snake_case(response.json())
    
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "icorp_api_get error")
        print(e)

def icorp_api_post(endpoint, data):
    headers = _get_icorp_headers()

    if "created_by" not in data or not data["created_by"]:
        try:
            data["created_by"] = frappe.session.user
        except Exception:
            data["created_by"] = "system-frappe"


    data = dict_keys_to_camel_case(data)
    data = remove_empty_fields(data)
    # data = convert_bools_to_bits(data)

    response = requests.post(f"{ICORP_API_BASE_URL}/{endpoint}", json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def icorp_api_put(endpoint, data):
    headers = _get_icorp_headers()

    if "modified_by" not in data or not data["modified_by"]:
        try:
            import frappe
            data["modified_by"] = frappe.session.user
        except Exception:
            data["modified_by"] = "system-frappe"


    data = dict_keys_to_camel_case(data)
    data = remove_empty_fields(data)

    response = requests.put(f"{ICORP_API_BASE_URL}/{endpoint}", json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def icorp_api_delete(endpoint, data=None): # Take a second look
    headers = _get_icorp_headers()

    if data:
        data = dict_keys_to_camel_case(data)
        data = remove_empty_fields(data)
        response = requests.delete(f"{ICORP_API_BASE_URL}/{endpoint}", json=data, headers=headers)
    else:
        response = requests.delete(f"{ICORP_API_BASE_URL}/{endpoint}", headers=headers)

    response.raise_for_status()
    if not response.text.strip():
        return {}
    return response.json()

# Headwind
def _get_headwind_headers():
    login = client.get_secret("Headwind-Privileged-Api-User").value
    password = client.get_secret("Headwind-Privileged-Api-User-Password").value
    password_md5 = hashlib.md5(password.encode('utf-8')).hexdigest().upper()

    payload = {"login": login, "password": password_md5}
    response = requests.post(f"{HEADWIND_API_BASE_URL}/public/jwt/login", json=payload)
    response.raise_for_status()
    token = response.json()["id_token"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    return headers

def headwind_api_get(endpoint, params=None):
    headers = _get_headwind_headers()
    response = requests.get(f"{HEADWIND_API_BASE_URL}/{endpoint}", headers=headers, params=params)
    response.raise_for_status()
    return response.json()

def headwind_api_post(endpoint, data=None):
    headers = _get_headwind_headers()
    response = requests.post(f"{HEADWIND_API_BASE_URL}/{endpoint}", headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def headwind_api_put(endpoint, data=None):
    headers = _get_headwind_headers()
    response = requests.put(f"{HEADWIND_API_BASE_URL}/{endpoint}", headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def headwind_api_delete(endpoint, data=None):
    headers = _get_headwind_headers()
    response = requests.delete(f"{HEADWIND_API_BASE_URL}/{endpoint}", headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def remove_empty_fields(data): # This should be moved out of here
    """Remove keys with None, empty string, or empty list values."""
    return {k: v for k, v in data.items() if v not in (None, "", [])}

