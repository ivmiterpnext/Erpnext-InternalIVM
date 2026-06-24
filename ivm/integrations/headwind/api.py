"""Headwind MDM API client."""

import hashlib

import frappe
import requests

from ivm.integrations.keyvault import get_config_value, get_secret_client
from ivm.machine_hardware_management.utils.case_utils import (dict_keys_to_camel_case, dict_keys_to_snake_case)

_LOG = "ivm.integrations.headwind"


def _get_base_url():
    url = get_config_value("HEADWIND_API_BASE_URL")
    if not url:
        frappe.throw("headwind_api_base_url is not set in site config or environment variables.")
    return url

def _fetch_headwind_token():
    client = get_secret_client()
    login = client.get_secret("Headwind-Privileged-Api-User").value
    password = client.get_secret("Headwind-Privileged-Api-User-Password").value
    password_md5 = hashlib.md5(password.encode("utf-8")).hexdigest().upper()

    response = requests.post(
        f"{_get_base_url()}/public/jwt/login",
        json={"login": login, "password": password_md5},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["id_token"]

def headwind_api_request(method, endpoint, data=None, params=None):
    log = frappe.logger(_LOG)
    method_upper = method.upper()

    try:
        log.debug(f"[HEADWIND {method_upper}] {endpoint} | data={data} | params={params}")

        token = _fetch_headwind_token()
        base_url = _get_base_url()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        full_url = f"{base_url}/{endpoint}"

        if data:
            data = dict_keys_to_camel_case(data)

        response = requests.request(
            method, full_url, headers=headers, json=data, params=params, timeout=120
        )

        if response.status_code == 401:
            log.warning(f"[HEADWIND {method_upper}] 401 on {endpoint}, retrying with new token")
            token = _fetch_headwind_token()
            headers["Authorization"] = f"Bearer {token}"
            response = requests.request(
                method, full_url, headers=headers, json=data, params=params, timeout=120
            )

        log.debug(f"[HEADWIND {method_upper}] {endpoint} → {response.status_code}")
        response.raise_for_status()

        return dict_keys_to_snake_case(response.json())

    except Exception:
        frappe.log_error(frappe.get_traceback(), f"headwind_api_request error [{method_upper} {endpoint}]")
        return None
