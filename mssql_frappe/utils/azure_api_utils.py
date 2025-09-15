from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from mssql_frappe.utils.case_utils import dict_keys_to_snake_case, dict_keys_to_camel_case, api_items_to_frappe_dict
import requests


API_BASE_URL = "https://dev.icorpapi.ivminc.com" # os.environ.get("ICORP_API_BASE_URL")
KEY_VAULT_URL = "https://ivm-apps-dev-kv-01.vault.azure.net//" # os.environ.get("AZURE_KEYVAULT_URL")
TENANT_ID = "5464da95-5a54-4466-8dde-04bd9e7f49da" # os.environ.get("AZURE_TENANT_ID")
API_SCOPE = "api://74c6b7f8-98fe-4907-8fac-93ebc38fc521/.default" # os.environ.get("AZURE_API_SCOPE")

def _get_azure_headers():
    client_id, client_secret = get_azure_client_credentials()
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

def get_azure_client_credentials():
    client_id = get_azure_secret("ICorpAPI-AzureAd-ClientId")
    client_secret = get_azure_secret("ICorpAPI-AzureAd-ClientSecret")
    return client_id, client_secret

def get_azure_secret(secret_name):
    credential = DefaultAzureCredential()
    client = SecretClient(vault_url=KEY_VAULT_URL, credential=credential)
    return client.get_secret(secret_name).value


def azure_api_get(url):
    try:
        headers = _get_azure_headers()
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        if not response.text.strip():
            return {}
            
        return dict_keys_to_snake_case(response.json())
    
    except Exception as e:
        print(e)

def azure_api_post(url, data):
    headers = _get_azure_headers()

    if "created_by" not in data or not data["created_by"]:
        try:
            import frappe
            data["created_by"] = frappe.session.user
        except Exception:
            data["created_by"] = "system-frappe"


    data = dict_keys_to_camel_case(data)
    data = remove_empty_fields(data)
    # data = convert_bools_to_bits(data)
    
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def azure_api_put(url, data):
    headers = _get_azure_headers()

    if "modified_by" not in data or not data["modified_by"]:
        try:
            import frappe
            data["modified_by"] = frappe.session.user
        except Exception:
            data["modified_by"] = "system-frappe"


    data = dict_keys_to_camel_case(data)
    data = remove_empty_fields(data)

    response = requests.put(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()

def azure_api_delete(url, data=None):
    headers = _get_azure_headers()

    if data:
        data = dict_keys_to_camel_case(data)
        data = remove_empty_fields(data)
        response = requests.delete(url, json=data, headers=headers)
    else:
        response = requests.delete(url, headers=headers)
        
    response.raise_for_status()
    if not response.text.strip():
        return {}
    return response.json()


def remove_empty_fields(data): # This should be moved out of here
    """Remove keys with None, empty string, or empty list values."""
    return {k: v for k, v in data.items() if v not in (None, "", [])}

def convert_bools_to_bits(data):
    # Recursively convert all boolean values in a dict to 0/1.
    if isinstance(data, dict):
        return {k: convert_bools_to_bits(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_bools_to_bits(item) for item in data]
    elif isinstance(data, bool):
        return int(data)
    else:
        return data