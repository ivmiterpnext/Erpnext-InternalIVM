"""
HubSpot API client — auth, retries, and typed helpers for CRM objects.
"""

import hashlib
import hmac
import time
from functools import lru_cache
from collections.abc import Callable
from typing import Any

import frappe
import requests
from ivm.integrations.hubspot.constants import (
    BIN_ASSOCIATION_KEY,
    BIN_PROPERTIES,
    BIN_TYPE_ID,
    DEAL_TYPE_ID,
    DEPLOYMENT_SITE_ASSOCIATION_KEY,
    DEPLOYMENT_SITE_TYPE_ID,
    MACHINE_PROPERTIES,
    MACHINE_TYPE_TO_ASSOCIATION_KEY,
    MACHINE_TYPES_WITH_BINS,
)

HUBSPOT_API_BASE = "https://api.hubapi.com"
DEFAULT_TIMEOUT_SECONDS = 30

_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 1.0
_SERVER_ERROR_CODES = frozenset({500, 502, 503, 504})


def _get_conf(key: str, label: str) -> str:
    """Return a site_config value or throw if missing."""

    value = frappe.conf.get(key)
    if not value:
        frappe.throw(f"HubSpot {label} not configured. Set '{key}' in site_config.json.")
    return str(value)


def _get_api_key() -> str:
    return _get_conf("hubspot_api_key", "API key")


def _get_portal_id() -> str:
    return _get_conf("hubspot_portal_id", "portal ID")


def _get_client_secret() -> str:
    return _get_conf("hubspot_client_secret", "client secret")


def _get_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_api_key()}"}


def _build_association_key(suffix: str) -> str:
    """Build the full association key: p{portal_id}_{suffix}."""
    return f"p{_get_portal_id()}_{suffix}"

def _server_error_backoff(attempt: int) -> None:
    time.sleep(_RETRY_BACKOFF_SECONDS * (2 ** attempt))


class HubSpotRateLimitExhausted(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"HubSpot rate limit hit. Suggested re-enqueue delay: {retry_after_seconds}s"
        )


def _retry_loop(
    send: Callable[[int], requests.Response],
) -> requests.Response:
    server_error_attempts = 0

    while True:
        try:
            response = send(server_error_attempts)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                delay = 10.0
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except (ValueError, TypeError):
                        pass
                delay = max(10.0, min(delay, 60.0))
                raise HubSpotRateLimitExhausted(delay)

            if response.status_code in _SERVER_ERROR_CODES:
                server_error_attempts += 1
                if server_error_attempts < _MAX_RETRIES:
                    _server_error_backoff(server_error_attempts - 1)
                    continue
                response.raise_for_status()

            response.raise_for_status()
            return response

        except HubSpotRateLimitExhausted:
            raise
        except requests.exceptions.RequestException:
            server_error_attempts += 1
            if server_error_attempts < _MAX_RETRIES:
                _server_error_backoff(server_error_attempts - 1)
            else:
                raise


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authed JSON request to the HubSpot API with retry."""

    url = f"{HUBSPOT_API_BASE}{path}"
    headers = {**_get_headers(), "Content-Type": "application/json"}

    def send(attempt: int) -> requests.Response:  # noqa: ARG001
        return requests.request(
            method, url, headers=headers, params=params,
            json=payload, timeout=DEFAULT_TIMEOUT_SECONDS,
        )

    return _retry_loop(send).json()


def _download(url: str) -> requests.Response:
    """Raw GET (no auth headers) with retry.  For pre-signed CDN URLs."""

    def send(attempt: int) -> requests.Response:  # noqa: ARG001
        return requests.get(url, timeout=DEFAULT_TIMEOUT_SECONDS)

    return _retry_loop(send)


def _get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """GET from the HubSpot API with retry."""
    return _request("GET", path, params=params)


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to the HubSpot API with retry."""
    return _request("POST", path, payload=payload)

def get_custom_object(
    object_type_id: str,
    object_id: int | str,
    properties: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch any CRM object by type and ID, optionally limiting properties."""

    params: dict[str, str] = {}
    if properties:
        params["properties"] = ",".join(properties)
    return _get(f"/crm/v3/objects/{object_type_id}/{object_id}", params or None)


def get_deal(deal_id: int | str, properties: list[str] | None = None) -> dict[str, Any]:
    """Fetch a HubSpot deal by ID."""
    return get_custom_object("deals", deal_id, properties)


def get_company(company_id: int | str, properties: list[str] | None = None) -> dict[str, Any]:
    """Fetch a HubSpot company by ID."""
    return get_custom_object("companies", company_id, properties)


def get_contact(contact_id: int | str, properties: list[str] | None = None) -> dict[str, Any]:
    """Fetch a HubSpot contact by ID."""
    return get_custom_object("contacts", contact_id, properties)


def get_machine(machine_type_id: str, machine_id: int | str) -> dict[str, Any]:
    """Fetch a machine custom object with its relevant properties."""
    props = MACHINE_PROPERTIES.get(machine_type_id, [])
    return get_custom_object(machine_type_id, machine_id, properties=props)


def get_bin(bin_id: int | str) -> dict[str, Any]:
    """Fetch a bin custom object with its properties."""
    return get_custom_object(BIN_TYPE_ID, bin_id, properties=BIN_PROPERTIES)


def get_associated_ids(
    object_type: str,
    object_id: int | str,
    association_type: str,
    association_key: str,
) -> list[str]:
    """Fetch association IDs for any object."""

    res = _get(
        f"/crm/v3/objects/{object_type}/{object_id}",
        params={"associations": association_type},
    )
    results = (
        res.get("associations", {})
        .get(association_key, {})
        .get("results", [])
    )
    return [r.get("id") for r in results if r.get("id")]


def get_deal_deployment_site_ids(deal_id: int | str) -> list[str]:
    """Fetch deployment site association IDs for a deal."""

    association_key = _build_association_key(DEPLOYMENT_SITE_ASSOCIATION_KEY)
    return get_associated_ids("deals", deal_id, DEPLOYMENT_SITE_TYPE_ID, association_key)


def get_deal_contact_ids(deal_id: int | str) -> list[str]:
    """Fetch contact association IDs for a deal."""
    return get_associated_ids("deals", deal_id, "contacts", "contacts")


def get_deal_company_ids(deal_id: int | str) -> list[str]:
    """Fetch company association IDs for a deal."""
    return get_associated_ids("deals", deal_id, "companies", "companies")


def get_site_machine_ids(site_id: int | str, machine_type_id: str) -> list[str]:
    """Fetch machine association IDs for a deployment site."""

    assoc_suffix = MACHINE_TYPE_TO_ASSOCIATION_KEY.get(machine_type_id, "")
    if not assoc_suffix:
        return []
    association_key = _build_association_key(assoc_suffix)
    return get_associated_ids(
        DEPLOYMENT_SITE_TYPE_ID, site_id, machine_type_id, association_key,
    )


def get_machine_bin_ids(machine_type_id: str, machine_id: int | str) -> list[str]:
    """Fetch bin association IDs for a machine."""

    if machine_type_id not in MACHINE_TYPES_WITH_BINS:
        return []
    association_key = _build_association_key(BIN_ASSOCIATION_KEY)
    return get_associated_ids(
        machine_type_id, machine_id, BIN_TYPE_ID, association_key,
    )


# ---------------------------------------------------------------------------
# Reverse association lookups (child → parent)
# ---------------------------------------------------------------------------


def get_site_deal_ids(site_id: int | str) -> list[str]:
    """Fetch deal IDs associated with a deployment site (reverse lookup)."""
    return get_associated_ids(
        DEPLOYMENT_SITE_TYPE_ID, site_id, "deals", "deals",
    )


def get_machine_site_ids(machine_type_id: str, machine_id: int | str) -> list[str]:
    """Fetch deployment site IDs associated with a machine (reverse lookup)."""
    site_assoc_key = _build_association_key(DEPLOYMENT_SITE_ASSOCIATION_KEY)
    return get_associated_ids(
        machine_type_id, machine_id, DEPLOYMENT_SITE_TYPE_ID, site_assoc_key,
    )


def get_bin_machine_ids(bin_id: int | str) -> list[tuple[str, str]]:
    """Fetch (machine_type_id, machine_id) pairs for a bin (reverse lookup).

    Checks all machine types that support bins and returns all matches.
    """
    results: list[tuple[str, str]] = []
    for machine_type_id in MACHINE_TYPES_WITH_BINS:
        assoc_suffix = MACHINE_TYPE_TO_ASSOCIATION_KEY.get(machine_type_id, "")
        if not assoc_suffix:
            continue
        assoc_key = _build_association_key(assoc_suffix)
        ids = get_associated_ids(BIN_TYPE_ID, bin_id, machine_type_id, assoc_key)
        for mid in ids:
            results.append((machine_type_id, mid))
    return results


def get_engagement_deal_ids(engagement_type: str, engagement_id: int | str) -> list[str]:
    """Fetch deal IDs associated with an engagement (reverse lookup)."""
    return get_associated_ids(engagement_type, engagement_id, "deals", "deals")


# ---------------------------------------------------------------------------
# Engagement / activity helpers
# ---------------------------------------------------------------------------


def get_deal_engagement_ids(deal_id: int | str, engagement_type: str) -> list[str]:
    """Fetch engagement IDs of *engagement_type* associated with a deal.

    Uses the CRM v3 associations endpoint to get IDs for a given engagement
    type (``notes``, ``calls``, ``emails``, ``tasks``, ``meetings``).
    """
    return get_associated_ids("deals", deal_id, engagement_type, engagement_type)


# Batch size limit for the CRM v4 batch associations endpoint.
_BATCH_ASSOCIATIONS_CHUNK_SIZE = 100


def get_deal_email_ids_batch(deal_ids: list[str]) -> dict[str, list[str]]:
    """Fetch email engagement IDs for multiple deals in a single API call.

    Uses the CRM v4 batch associations endpoint, which accepts up to 100 deal
    IDs per request.  Returns a dict mapping deal_id → list of email IDs.

    This is the efficient alternative to calling ``get_deal_engagement_ids``
    once per deal — the total API cost is ``ceil(len(deal_ids) / 100)`` calls
    regardless of how many deals or emails are involved.
    """
    result: dict[str, list[str]] = {did: [] for did in deal_ids}

    # Process in chunks of 100 (API limit).
    for i in range(0, len(deal_ids), _BATCH_ASSOCIATIONS_CHUNK_SIZE):
        chunk = deal_ids[i: i + _BATCH_ASSOCIATIONS_CHUNK_SIZE]
        response = _post(
            "/crm/v4/associations/deals/emails/batch/read",
            {"inputs": [{"id": did} for did in chunk]},
        )
        for entry in response.get("results", []):
            deal_id = str(entry["from"]["id"])
            email_ids = [str(to["toObjectId"]) for to in entry.get("to", [])]
            result[deal_id] = email_ids

    return result


def get_engagement(
    engagement_type: str,
    engagement_id: int | str,
    properties: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch a single engagement object by type and ID."""
    return get_custom_object(engagement_type, engagement_id, properties)


def download_file(file_id: str) -> tuple[str, bytes] | None:
    """Download a file from HubSpot's Files API.

    Returns ``(filename, content_bytes)`` on success, or ``None`` on failure.

    HIDDEN_PRIVATE files (the default for CRM email attachments) cannot be
    downloaded via ``defaultHostingUrl`` or the legacy signed-url-redirect
    endpoint.  The correct approach is the Files v3 ``/signed-url`` endpoint,
    which returns a time-limited pre-signed CDN URL that works without auth.
    """
    try:
        meta = _get(f"/files/v3/files/{file_id}")
        name = meta.get("name", f"hubspot_file_{file_id}")
        extension = meta.get("extension", "")
        if extension and not name.endswith(f".{extension}"):
            name = f"{name}.{extension}"

        # Get a pre-signed download URL valid for this request.
        signed = _get(f"/files/v3/files/{file_id}/signed-url")
        cdn_url = signed.get("url")
        if not cdn_url:
            frappe.logger("hubspot").warning(
                f"No signed URL returned for HubSpot file {file_id}"
            )
            return None

        # The pre-signed URL includes auth in the query string — no headers needed.
        response = _download(cdn_url)
        return (name, response.content)
    except Exception:
        frappe.logger("hubspot").warning(
            f"Failed to download HubSpot file {file_id}: "
            f"{frappe.get_traceback(with_context=False)}"
        )
        return None


@lru_cache(maxsize=512)
def get_owner_email(owner_id: int | str) -> str | None:
    """Fetch the email for a HubSpot owner, or None if unresolvable.

    Results are cached in-memory (up to 512 entries) so repeated calls for
    the same owner ID within a single worker process don't hit the API again.
    """
    try:
        data = _get(f"/crm/v3/owners/{owner_id}")
        return data.get("email") or None
    except Exception:
        frappe.logger("hubspot").warning(
            f"Could not resolve HubSpot owner {owner_id}"
        )
        return None


def search_deals(
    filters: list[dict],
    properties: list[str],
    after: str | None = None,
) -> dict[str, Any]:
    """POST to /crm/v3/objects/deals/search with cursor-based pagination.

    Args:
        filters: HubSpot filter dicts (combined into a single filterGroup).
        properties: HubSpot property names to include in each result.
        after: Pagination cursor from paging.next.after of the previous response.

    Returns the raw HubSpot search response dict.
    """
    payload: dict[str, Any] = {
        "filterGroups": [{"filters": filters}],
        "properties": properties,
        "limit": 100,
    }
    if after:
        payload["after"] = after
    return _post("/crm/v3/objects/deals/search", payload)


def search_contacts(
    filters: list[dict],
    properties: list[str],
    after: str | None = None,
) -> dict[str, Any]:
    """POST to /crm/v3/objects/contacts/search with cursor-based pagination.

    Args:
        filters: HubSpot filter dicts (combined into a single filterGroup).
        properties: HubSpot property names to include in each result.
        after: Pagination cursor from paging.next.after of the previous response.

    Returns the raw HubSpot search response dict.
    """
    payload: dict[str, Any] = {
        "filterGroups": [{"filters": filters}],
        "properties": properties,
        "limit": 100,
    }
    if after:
        payload["after"] = after
    return _post("/crm/v3/objects/contacts/search", payload)


@frappe.whitelist()
def get_hubspot_deal_url(deal_id: int | str) -> str:
    """Build the full HubSpot deal URL from deal ID and configured portal ID."""

    portal_id = _get_portal_id()
    return f"https://app-na2.hubspot.com/contacts/{portal_id}/record/{DEAL_TYPE_ID}/{deal_id}"


def verify_signature(request_body: str, real_hash: str) -> bool:
    """Validate a HubSpot webhook signature (SHA-256 of client_secret + body)."""
    
    client_secret = _get_client_secret()
    source_string = (client_secret + request_body).encode("utf-8")
    hashed = hashlib.sha256(source_string).hexdigest()
    return hmac.compare_digest(hashed, real_hash)
