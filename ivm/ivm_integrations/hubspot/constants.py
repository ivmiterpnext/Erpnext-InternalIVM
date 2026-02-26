"""HubSpot integration constants."""

from __future__ import annotations

from collections.abc import Mapping

HUBSPOT_WEBHOOK_TIMESTAMP_HEADER = "X-HubSpot-Request-Timestamp"
HUBSPOT_WEBHOOK_SIGNATURE_HEADER = "X-HubSpot-Signature-v3"

HUBSPOT_EVENT_SUBSCRIPTION_TYPES: tuple[str, ...] = (
	"deal.creation",
	"deal.propertyChange",
)

HUBSPOT_DEAL_PROPERTY_KEYS: Mapping[str, str] = {
	"name": "dealname",
	"amount": "amount",
	"close_date": "closedate",
	"stage_id": "dealstage",
	"owner_id": "hubspot_owner_id",
	"pipeline_id": "pipeline",
	"last_modified": "hs_lastmodifieddate",
}

WEBHOOK_ALLOWED_TIMESTAMP_SKEW_SECONDS = 300
