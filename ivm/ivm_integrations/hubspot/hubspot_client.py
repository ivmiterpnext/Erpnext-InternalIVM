"""
HubSpot API client — auth, retries, and typed helpers for CRM objects.
"""

import hashlib
import time
from typing import Any
import frappe
import requests
from ivm.ivm_integrations.hubspot.constants import (
    BIN_PROPERTIES,
    BIN_TYPE_ID,
    DEAL_TYPE_ID,
    DEPLOYMENT_SITE_TYPE_ID,
    MACHINE_PROPERTIES,
    MACHINE_TYPE_TO_ASSOCIATION_KEY,
    MACHINE_TYPE_TO_CHILD_TABLE,
    MACHINE_TYPES_WITH_BINS,
)

HUBSPOT_API_BASE = "https://api.hubapi.com"
DEFAULT_TIMEOUT_SECONDS = 30

DEPLOYMENT_SITE_ASSOCIATION_KEY_SUFFIX = "deployment_sites"
BIN_ASSOCIATION_KEY_SUFFIX = "bins"

# Retry settings for transient failures (429, 500, 502, 503, 504).
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 1.0
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


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

def _get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    """GET from the HubSpot API with automatic retry on transient errors."""

    url = f"{HUBSPOT_API_BASE}{path}"
    headers = _get_headers()

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                _backoff(attempt, response)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_SECONDS * (2 ** attempt))
            else:
                raise

    # Should not be reachable, but keeps type-checkers happy.
    raise last_exc  # type: ignore[misc]

def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST to the HubSpot API with automatic retry on transient errors."""

    url = f"{HUBSPOT_API_BASE}{path}"
    headers = {**_get_headers(), "Content-Type": "application/json"}

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = requests.post(
                url, headers=headers, json=payload, timeout=DEFAULT_TIMEOUT_SECONDS,
            )
            if response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                _backoff(attempt, response)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_SECONDS * (2 ** attempt))
            else:
                raise

    raise last_exc  # type: ignore[misc]


def _backoff(attempt: int, response: requests.Response) -> None:
    """Sleep before the next retry, respecting Retry-After when available."""

    delay = _RETRY_BACKOFF_SECONDS * (2 ** attempt)
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            delay = float(retry_after)
        except (ValueError, TypeError):
            pass
    time.sleep(delay)

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

    association_key = _build_association_key(DEPLOYMENT_SITE_ASSOCIATION_KEY_SUFFIX)
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
    association_key = _build_association_key(BIN_ASSOCIATION_KEY_SUFFIX)
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
    site_assoc_key = _build_association_key(DEPLOYMENT_SITE_ASSOCIATION_KEY_SUFFIX)
    return get_associated_ids(
        machine_type_id, machine_id, DEPLOYMENT_SITE_TYPE_ID, site_assoc_key,
    )


def get_bin_machine_ids(bin_id: int | str) -> list[tuple[str, str]]:
    """Fetch (machine_type_id, machine_id) pairs for a bin (reverse lookup).

    Checks all machine types that support bins.  Returns the first match
    since a bin typically belongs to a single machine.
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
        response = requests.get(cdn_url, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return (name, response.content)
    except Exception:
        frappe.logger("hubspot").warning(
            f"Failed to download HubSpot file {file_id}: "
            f"{frappe.get_traceback(with_context=False)}"
        )
        return None


# In-memory cache for owner ID → email resolution within a worker process.
_owner_email_cache: dict[str, str | None] = {}


def get_owner_email(owner_id: int | str) -> str | None:
    """Fetch the email for a HubSpot owner, or None if unresolvable.

    Results are cached in-memory so repeated calls for the same owner ID
    within a single worker process don't hit the HubSpot API again.
    """
    key = str(owner_id)
    if key in _owner_email_cache:
        return _owner_email_cache[key]

    try:
        data = _get(f"/crm/v3/owners/{key}")
        email = data.get("email") or None
    except Exception:
        frappe.logger("hubspot").warning(
            f"Could not resolve HubSpot owner {owner_id}"
        )
        email = None

    _owner_email_cache[key] = email
    return email


@frappe.whitelist()
def get_hubspot_deal_url(deal_id: int | str) -> str:
    """Build the full HubSpot deal URL from deal ID and configured portal ID."""

    portal_id = _get_portal_id()
    return f"https://app-na2.hubspot.com/contacts/{portal_id}/record/0-3/{deal_id}"


def verify_signature(request_body: str, real_hash: str) -> bool:
    """Validate a HubSpot webhook signature (SHA-256 of client_secret + body)."""
    
    client_secret = _get_client_secret()
    source_string = (client_secret + request_body).encode("utf-8")
    hashed = hashlib.sha256(source_string).hexdigest()
    return hashed == real_hash
