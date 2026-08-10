"""iCorp API client — authentication, CRUD helpers, and response utilities."""

from typing import Any

import frappe
import requests

from ivm.integrations.keyvault import get_config_value, get_secrets
from ivm.integrations.icorp.utils import (
	dict_keys_to_camel_case,
	dict_keys_to_snake_case,
)
from ivm.machine_hardware_management.utils.filter_utils import filters_to_query_params

_LOG = "ivm.integrations.icorp"


def _get_base_url() -> str:
    """Return the iCorp API base URL from site config or environment."""
    url = get_config_value("ICORP_API_BASE_URL")
    if not url:
        frappe.throw("icorp_api_base_url is not set in site config or environment variables.")
    return url


def _get_tenant_id() -> str:
    """Return the Azure AD tenant ID from site config or environment."""
    tenant_id = get_config_value("AZURE_TENANT_ID")
    if not tenant_id:
        frappe.throw("azure_tenant_id is not set in site config or environment variables.")
    return tenant_id


def _get_api_scope() -> str:
    """Return the iCorp API OAuth scope from site config or environment."""
    scope = get_config_value("ICORP_API_SCOPE")
    if not scope:
        frappe.throw("icorp_api_scope is not set in site config or environment variables.")
    return scope


def get_icorp_auth() -> tuple[str, dict[str, str]]:
    """Authenticate via Azure AD ROPC flow and return ``(base_url, headers)``."""
    secrets = get_secrets([
        "ICorpAPI-AzureAd-ClientId",
        "ICorpAPI-AzureAd-ClientSecret",
        "FrappeServiceAccount-Username",
        "FrappeServiceAccount-Password",
    ])
    client_id = secrets["ICorpAPI-AzureAd-ClientId"]
    client_secret = secrets["ICorpAPI-AzureAd-ClientSecret"]
    username = secrets["FrappeServiceAccount-Username"]
    password = secrets["FrappeServiceAccount-Password"]

    tenant_id = _get_tenant_id()
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    response = requests.post(token_url, data={
        "grant_type":    "password",
        "client_id":     client_id,
        "client_secret": client_secret,
        "username":      username,
        "password":      password,
        "scope":         _get_api_scope(),
    }, timeout=30)

    response.raise_for_status()

    return _get_base_url(), {
        "Authorization": f"Bearer {response.json()['access_token']}",
        "Content-Type":  "application/json",
    }


def icorp_api_get(endpoint: str) -> dict[str, Any]:
    """Perform an authenticated GET request to the iCorp API.

    Response keys are converted to snake_case.  Raises on HTTP errors,
    timeouts, and non-JSON responses.
    """
    log = frappe.logger(_LOG)
    base_url, headers = get_icorp_auth()
    full_url = f"{base_url}/{endpoint}"
    log.debug(f"[ICORP GET] {endpoint}")

    try:
        response = requests.get(full_url, headers=headers, timeout=120)
        log.debug(f"[ICORP GET] {endpoint} → {response.status_code}")

        try:
            response_json = response.json()
        except ValueError:
            frappe.throw(f"ICorp API returned non-JSON response for {endpoint}: {response.text}")

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            frappe.throw(f"ICorp API Error: {_extract_error_message(response) or str(e)}")

        return dict_keys_to_snake_case(response_json)

    except requests.exceptions.Timeout:
        frappe.throw(f"ICorp API Timeout: {full_url} timed out after 120 seconds")
    except requests.exceptions.RequestException as e:
        frappe.throw(f"ICorp API Request Error: {str(e)}")


def icorp_api_post(endpoint: str, data: dict[str, Any], headers: dict | None = None) -> dict[str, Any]:
    """Perform an authenticated POST request to the iCorp API.

    Payload keys are converted to camelCase and empty fields are stripped
    before sending.  Returns the raw JSON response (no snake_case conversion).
    """
    log = frappe.logger(_LOG)
    base_url, headers = get_icorp_auth()

    data = _remove_empty_fields(dict_keys_to_camel_case(data))
    url = f"{base_url}/{endpoint}"
    log.debug(f"[ICORP POST] {endpoint} | data={data}")

    response = requests.post(url, json=data, headers=headers, timeout=120)
    log.debug(f"[ICORP POST] {endpoint} → {response.status_code}")

    try:
        return response.json()
    except ValueError:
        frappe.log_error(f"Non-JSON response from {url}: {response.text}", "ICorp API POST Error")
        return {"error": "Invalid JSON response", "status_code": response.status_code, "text": response.text}


def icorp_api_put(endpoint: str, data: dict[str, Any]) -> dict[str, Any] | None:
    """Perform an authenticated PUT request to the iCorp API.

    Payload keys are converted to camelCase and empty fields are stripped.
    Raises on HTTP errors.
    """
    log = frappe.logger(_LOG)
    base_url, headers = get_icorp_auth()

    data = _remove_empty_fields(dict_keys_to_camel_case(data))
    url = f"{base_url}/{endpoint}"
    log.debug(f"[ICORP PUT] {endpoint} | data={data}")

    response = requests.put(url, json=data, headers=headers, timeout=120)
    log.debug(f"[ICORP PUT] {endpoint} → {response.status_code}")

    try:
        response_json = response.json()
    except ValueError:
        response_json = None

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        frappe.throw(f"ICorp API Error: {_extract_error_message(response) or str(e)}")

    return response_json


def icorp_api_delete(endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Perform an authenticated DELETE request to the iCorp API.

    Accepts an optional JSON body.  Raises on HTTP errors.
    """
    log = frappe.logger(_LOG)
    base_url, headers = get_icorp_auth()
    url = f"{base_url}/{endpoint}"
    log.debug(f"[ICORP DELETE] {endpoint}" + (f" | data={data}" if data else ""))

    if data:
        data = _remove_empty_fields(dict_keys_to_camel_case(data))
        response = requests.delete(url, json=data, headers=headers, timeout=120)
    else:
        response = requests.delete(url, headers=headers, timeout=120)

    log.debug(f"[ICORP DELETE] {endpoint} → {response.status_code}")

    try:
        response_json = response.json()
    except ValueError:
        response_json = None

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        frappe.throw(f"ICorp API Error: {_extract_error_message(response) or str(e)}")

    return response_json


def icorp_get_count(endpoint: str, filters: list | None = None) -> int:
    """Return the total record count for an endpoint, applying optional filters.

    Uses a single-record page request and reads the ``pagination.total_records``
    value from the response.  Returns ``0`` on any error.
    """
    try:
        url = f"{endpoint}?page=1&pageSize=1"
        filter_query = filters_to_query_params(filters)
        if filter_query:
            url += f"&{filter_query}"

        result = icorp_api_get(url)
        total_records = result.get("pagination", {}).get("total_records")
        return int(total_records) if total_records is not None else 0
    except Exception:
        frappe.log_error(frappe.get_traceback(), "icorp_get_count error")
        return 0


def extract_id(response: dict | None, entity_type: str) -> int | None:
    """Extract an entity ID from an iCorp API response.

    Unwraps a ``"data"`` envelope if present, then tries common key
    patterns: ``id``, ``{entity_type}Id``, ``{entity_type}_id``, ``Id``.
    Returns ``None`` if no ID can be found.
    """
    if not isinstance(response, dict):
        return None

    if "data" in response and isinstance(response["data"], dict):
        response = response["data"]

    for key in ("id", f"{entity_type}Id", f"{entity_type}_id", "Id"):
        if key in response and response[key] is not None:
            try:
                return int(response[key])
            except (ValueError, TypeError):
                pass

    frappe.logger(_LOG).warning(
        f"Could not extract {entity_type} ID from iCorp response. "
        f"Keys: {list(response.keys())}"
    )
    return None


def _extract_error_message(response: requests.Response) -> str:
    """Best-effort extraction of an error message from an iCorp HTTP response."""
    try:
        error_json = response.json()
        return error_json.get("message") or str(error_json)
    except Exception:
        return response.text


def _remove_empty_fields(data: dict) -> dict:
    """Strip keys whose values are ``None``, ``""``, or ``[]``."""
    return {k: v for k, v in data.items() if v not in (None, "", [])}
