from typing import Any
import time
import frappe
import requests
import re

HUBSPOT_API_BASE = "https://api.hubapi.com"
DEFAULT_TIMEOUT_SECONDS = 30

DEAL_PROPERTIES = (
	"dealname",
	"amount",
	"dealstage",
	"closedate",
	"pipeline",
	"hubspot_owner_id",
)


def _get_api_key() -> str:
	api_key = frappe.conf.get("hubspot_api_key")
	if not api_key:
		frappe.throw("HubSpot API key not configured. Set 'hubspot_api_key' in site_config.json.")
	return str(api_key)


def _get_client_secret() -> str:
	client_secret = frappe.conf.get("hubspot_client_secret")
	if not client_secret:
		frappe.throw("HubSpot client secret not configured. Set 'hubspot_client_secret' in site_config.json.")
	return str(client_secret)


def _get_headers() -> dict[str, str]:
	return {
		"Authorization": f"Bearer {_get_api_key()}",
		# "Content-Type": "application/json",
	}


def get_deal(deal_id: int | str) -> dict[str, Any]:
	"""Fetch a HubSpot deal by ID with standard properties.

	GET /crm/v3/objects/deals/{deal_id}?properties=...
	"""
	url = f"https://api.hubapi.com/crm/v3/objects/deals/{deal_id}"

	response = requests.get(
		url,
		headers=_get_headers(),
		# timeout=DEFAULT_TIMEOUT_SECONDS,
	)
	response.raise_for_status()
	res = response.json()
	return res


def get_deal_associations(deal_id: int | str) -> list[str]:
	url = f'https://api.hubapi.com/crm/v3/objects/deals/{deal_id}?associations=2-226377266'

	response = requests.get(
		url,
		headers=_get_headers(),
		# timeout=DEFAULT_TIMEOUT_SECONDS,
	)
	response.raise_for_status()
	res = response.json()

	all_associations = res.get("associations", {})
	resp_url = res.get("url")
	match = re.search(r"contacts/(\d+)/record/", resp_url)
	if match == None:
		frappe.throw("Invalid Contact Id to get Associations")
	results = all_associations.get("p244312848_deployment_sites", {}).get("results", [])

	association_ids: list[str] = []
	for association in results:
		association_ids.append(association.get("id"))

	return association_ids


def get_custom_object(
	object_type_id: str,
	object_id: int | str,
) -> dict[str, Any]:
	"""Fetch a custom object (e.g. deployment_site) by type ID and object ID.

	GET /crm/v3/objects/{object_type_id}/{object_id}
	"""
	url = f"https://api.hubapi.com/crm/v3/objects/{object_type_id}/{object_id}"

	response = requests.get(
		url,
		headers=_get_headers(),
		timeout=DEFAULT_TIMEOUT_SECONDS,
	)
	response.raise_for_status()
	return response.json()


def verify_signature(request_body: str, real_hash: str) -> bool:
	import hashlib

	client_secret = _get_client_secret()
	source_string = (client_secret+request_body).encode("utf-8")

	hashed = hashlib.sha256(source_string).hexdigest()

	return hashed == real_hash
