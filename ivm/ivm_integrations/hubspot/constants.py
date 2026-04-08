from collections.abc import Mapping

HUBSPOT_WEBHOOK_TIMESTAMP_HEADER = "X-HubSpot-Request-Timestamp"
HUBSPOT_WEBHOOK_SIGNATURE_HEADER = "X-HubSpot-Signature-v3"

HUBSPOT_EVENT_SUBSCRIPTION_TYPES: tuple[str, ...] = (
	"deal.creation",
	"deal.propertyChange",
)

HUBSPOT_DEAL_CREATION_SUBSCRIPTION_TYPE = "deal.creation"
HUBSPOT_DEAL_PROPERTY_CHANGE_SUBSCRIPTION_TYPE = "deal.propertyChange"

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

HUBSPOT_API_BASE_URL = "https://api.hubapi.com"
HUBSPOT_DEPLOYMENT_SITES_OBJECT_TYPE = "deployment_sites"
HUBSPOT_CLOSEDWON_PROPERTY_VALUE = "closedwon"

# CRM v3 endpoint template for fetching a single custom object by ID.
# Usage: HUBSPOT_CUSTOM_OBJECT_URL.format(object_type=..., object_id=...)
HUBSPOT_CUSTOM_OBJECT_URL = "/crm/v3/objects/{object_type}/{object_id}"
