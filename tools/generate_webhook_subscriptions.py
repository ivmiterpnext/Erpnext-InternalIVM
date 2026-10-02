#!/usr/bin/env python3
"""Generate webhook subscription JSON for the IVM HubSpot integration app.

Reads field-map constants from ivm.integrations.hubspot.constants and
routing targets from ivm.integrations.hubspot.routing, then emits a
complete webhooks-hsmeta.json file with all object types and properties.

Usage:
    python generate_webhook_subscriptions.py --active=false --out <path>
    python generate_webhook_subscriptions.py --active=true --out <path> --base-url https://example.com
"""

import argparse
import json
import sys
from collections import OrderedDict
from typing import Any

# Import from ivm (requires bench Python environment)
from ivm.integrations.hubspot.constants import (
	BIN_ASSOCIATION_KEY,
	BIN_FIELD_MAP,
	BIN_PROPERTIES,
	BIN_TYPE_ID,
	CALL_PROPERTIES,
	CALL_TYPE_ID,
	COMPANY_FIELD_MAP,
	COMPANY_PROPERTIES,
	COMPANY_TYPE_ID,
	CONTACT_PROPERTIES,
	CONTACT_TYPE_ID,
	DEAL_FIELD_MAP,
	DEAL_TYPE_ID,
	DEPLOYMENT_SITE_ASSOCIATION_KEY,
	DEPLOYMENT_SITE_TYPE_ID,
	EMAIL_PROPERTIES,
	EMAIL_TYPE_ID,
	EMAIL_WEBHOOK_UNSUPPORTED_PROPERTIES,
	ENGAGEMENT_PROPERTIES,
	ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID,
	MACHINE_PROPERTIES,
	MACHINE_TYPE_TO_ASSOCIATION_KEY,
	MEETING_PROPERTIES,
	MEETING_TYPE_ID,
	NOTE_PROPERTIES,
	NOTE_TYPE_ID,
	SITE_FIELD_MAP,
	SMARTCENTER_ASSOCIATION_KEY,
	SMARTCENTER_TYPE_ID,
	SMARTLOCKER_ASSOCIATION_KEY,
	SMARTLOCKER_TYPE_ID,
	SMARTSTATION_ASSOCIATION_KEY,
	SMARTSTATION_TYPE_ID,
	SMARTSYNC_ASSOCIATION_KEY,
	SMARTSYNC_TYPE_ID,
	SMARTVAULT_ASSOCIATION_KEY,
	SMARTVAULT_TYPE_ID,
	TASK_PROPERTIES,
	TASK_TYPE_ID,
)
from ivm.integrations.hubspot.routing import SYNC_TARGETS


def _dedupe_properties(props: list[str]) -> list[str]:
	"""Deduplicate properties while preserving first occurrence order."""
	seen = set()
	result = []
	for prop in props:
		if prop not in seen:
			seen.add(prop)
			result.append(prop)
	return result


def _build_type_id_to_name() -> dict[str, str]:
	"""Build TYPE_ID_TO_NAME mapping from constants."""
	return {
		DEAL_TYPE_ID: "DEAL",
		CONTACT_TYPE_ID: "CONTACT",
		COMPANY_TYPE_ID: "COMPANY",
		NOTE_TYPE_ID: "NOTE",
		CALL_TYPE_ID: "CALL",
		EMAIL_TYPE_ID: "EMAIL",
		TASK_TYPE_ID: "TASK",
		MEETING_TYPE_ID: "MEETING_EVENT",
		DEPLOYMENT_SITE_TYPE_ID: DEPLOYMENT_SITE_ASSOCIATION_KEY,
		BIN_TYPE_ID: BIN_ASSOCIATION_KEY,
		SMARTSTATION_TYPE_ID: SMARTSTATION_ASSOCIATION_KEY,
		SMARTLOCKER_TYPE_ID: SMARTLOCKER_ASSOCIATION_KEY,
		SMARTSYNC_TYPE_ID: SMARTSYNC_ASSOCIATION_KEY,
		SMARTVAULT_TYPE_ID: SMARTVAULT_ASSOCIATION_KEY,
		SMARTCENTER_TYPE_ID: SMARTCENTER_ASSOCIATION_KEY,
	}


def _validate_type_ids(type_id_to_name: dict[str, str]) -> None:
	"""Validate that every key in SYNC_TARGETS has a TYPE_ID_TO_NAME entry."""
	missing = set(SYNC_TARGETS.keys()) - set(type_id_to_name.keys())
	if missing:
		raise SystemExit(f"Missing TYPE_ID_TO_NAME entries for: {', '.join(sorted(missing))}")


def _get_properties_for_type(type_id: str) -> list[str]:
	"""Get the property list for a given object type ID."""
	if type_id == DEAL_TYPE_ID:
		return list(DEAL_FIELD_MAP.keys())
	elif type_id == CONTACT_TYPE_ID:
		return CONTACT_PROPERTIES
	elif type_id == COMPANY_TYPE_ID:
		return COMPANY_PROPERTIES
	elif type_id == DEPLOYMENT_SITE_TYPE_ID:
		return list(SITE_FIELD_MAP.keys())
	elif type_id in MACHINE_PROPERTIES:
		return _dedupe_properties(MACHINE_PROPERTIES[type_id])
	elif type_id == BIN_TYPE_ID:
		return BIN_PROPERTIES
	elif type_id in ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID:
		engagement_type = ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID[type_id]
		props = ENGAGEMENT_PROPERTIES.get(engagement_type, [])
		# Exclude EMAIL properties that HubSpot doesn't support for webhook subscriptions
		if engagement_type == "emails":
			props = [p for p in props if p not in EMAIL_WEBHOOK_UNSUPPORTED_PROPERTIES]
		return props
	else:
		return []


def _make_entry(
	active: bool, object_type: str, subscription_type: str, property_name: str | None = None
) -> dict[str, Any]:
	"""Create a single subscription entry with correct key order."""
	entry = OrderedDict()
	entry["active"] = active
	entry["objectType"] = object_type
	if property_name is not None:
		entry["propertyName"] = property_name
	entry["subscriptionType"] = subscription_type
	return entry


def generate_subscriptions(active: bool, base_url: str) -> dict[str, Any]:
	"""Generate the complete webhooks-hsmeta.json structure."""
	type_id_to_name = _build_type_id_to_name()
	_validate_type_ids(type_id_to_name)

	# Order of object types: DEAL, CONTACT, COMPANY, deployment_sites, machines, bins, engagements
	type_order = [
		DEAL_TYPE_ID,
		CONTACT_TYPE_ID,
		COMPANY_TYPE_ID,
		DEPLOYMENT_SITE_TYPE_ID,
		SMARTSTATION_TYPE_ID,
		SMARTLOCKER_TYPE_ID,
		SMARTSYNC_TYPE_ID,
		SMARTVAULT_TYPE_ID,
		SMARTCENTER_TYPE_ID,
		BIN_TYPE_ID,
		NOTE_TYPE_ID,
		CALL_TYPE_ID,
		EMAIL_TYPE_ID,
		TASK_TYPE_ID,
		MEETING_TYPE_ID,
	]

	subscriptions = []

	for type_id in type_order:
		if type_id not in SYNC_TARGETS:
			continue

		object_type_name = type_id_to_name[type_id]

		# object.creation entry
		subscriptions.append(_make_entry(active, object_type_name, "object.creation"))

		# object.propertyChange entries (sorted alphabetically)
		properties = _get_properties_for_type(type_id)
		for prop in sorted(properties):
			subscriptions.append(_make_entry(active, object_type_name, "object.propertyChange", prop))

	# Add exactly one object.associationChange entry for DEAL
	subscriptions.append(_make_entry(active, "DEAL", "object.associationChange"))

	return {
		"uid": "ivm_hubspot_integration_webhooks",
		"type": "webhooks",
		"config": {
			"settings": {
				"targetUrl": f"{base_url}/api/method/ivm.integrations.hubspot.webhook.handle_webhook",
				"maxConcurrentRequests": 10,
			},
			"subscriptions": {"crmObjects": subscriptions},
		},
	}


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Generate webhook subscription JSON for IVM HubSpot integration."
	)
	parser.add_argument(
		"--active",
		required=True,
		type=str,
		help="Subscription active state: 'true' or 'false' (case-insensitive)",
	)
	parser.add_argument(
		"--out",
		required=True,
		type=str,
		help="Output file path",
	)
	parser.add_argument(
		"--base-url",
		default="https://portal.ivminc.com",
		type=str,
		help="Base URL for webhook targetUrl (default: https://portal.ivminc.com)",
	)

	args = parser.parse_args()

	# Parse --active
	active_str = args.active.lower()
	if active_str == "true":
		active = True
	elif active_str == "false":
		active = False
	else:
		raise SystemExit(f"--active must be 'true' or 'false', got '{args.active}'")

	# Generate and write
	data = generate_subscriptions(active, args.base_url)

	with open(args.out, "w") as f:
		json.dump(data, f, indent=2)
		f.write("\n")


if __name__ == "__main__":
	main()
