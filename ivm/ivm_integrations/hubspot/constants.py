"""
Shared constants for the HubSpot integration package.
"""

from ivm.deals.constants import (
    SKIP_CHILD_FIELDS,  # noqa: F401 — re-exported for backward compatibility
    TABLE_TO_DOCTYPE,
    TABLE_TO_QUANTITY,
)

# Service account used for all HubSpot-initiated writes so that activity
# logs clearly attribute changes to the integration rather than "Guest".
HUBSPOT_USER = "hubspot@ivm.local"
HUBSPOT_ROLE = "Integration"

# Weeks to add to the deal close date to calculate the target ship date.
TARGET_SHIP_WEEKS = 5

# ---------------------------------------------------------------------------
# HubSpot custom object type IDs
# ---------------------------------------------------------------------------

DEPLOYMENT_SITE_TYPE_ID = "2-226377266"
SMARTSTATION_TYPE_ID = "2-230236986"
SMARTLOCKER_TYPE_ID = "2-230363982"
SMARTSYNC_TYPE_ID = "2-230364924"
SMARTVAULT_TYPE_ID = "2-230365132"
SMARTCENTER_TYPE_ID = "2-230365088"
BIN_TYPE_ID = "2-230364465"

# ---------------------------------------------------------------------------
# HubSpot association key suffixes (prefixed with p{portal_id}_)
# ---------------------------------------------------------------------------

DEPLOYMENT_SITE_ASSOCIATION_KEY = "deployment_sites"
SMARTSTATION_ASSOCIATION_KEY = "smartstations"
SMARTLOCKER_ASSOCIATION_KEY = "smartlockers"
SMARTSYNC_ASSOCIATION_KEY = "smartsyncs"
SMARTVAULT_ASSOCIATION_KEY = "smartvaults"
SMARTCENTER_ASSOCIATION_KEY = "smartcenters"
BIN_ASSOCIATION_KEY = "bins"

# Machine types that have bin associations
MACHINE_TYPES_WITH_BINS = frozenset({
    SMARTLOCKER_TYPE_ID,
    SMARTSYNC_TYPE_ID,
    SMARTVAULT_TYPE_ID,
})

# ---------------------------------------------------------------------------
# Machine type to child table mappings (derived from deals.constants)
# ---------------------------------------------------------------------------

# Maps HubSpot custom object type ID to child table fieldname on
# Deployment Location.  The fieldnames come from deals.constants.
MACHINE_TYPE_TO_CHILD_TABLE: dict[str, str] = {
    SMARTSTATION_TYPE_ID: "smartstation_details",
    SMARTLOCKER_TYPE_ID: "smartlocker_details",
    SMARTSYNC_TYPE_ID: "smartsync_details",
    SMARTVAULT_TYPE_ID: "smartvault_details",
    SMARTCENTER_TYPE_ID: "smartcenter_details",
}

# Maps HubSpot custom object type ID to child table DocType name,
# derived from the canonical TABLE_TO_DOCTYPE in deals.constants.
MACHINE_TYPE_TO_CHILD_DOCTYPE: dict[str, str] = {
    hs_type: TABLE_TO_DOCTYPE[table_field]
    for hs_type, table_field in MACHINE_TYPE_TO_CHILD_TABLE.items()
}

# Machine type to association key suffix (used to build p{portal_id}_{suffix})
MACHINE_TYPE_TO_ASSOCIATION_KEY: dict[str, str] = {
    SMARTSTATION_TYPE_ID: SMARTSTATION_ASSOCIATION_KEY,
    SMARTLOCKER_TYPE_ID: SMARTLOCKER_ASSOCIATION_KEY,
    SMARTSYNC_TYPE_ID: SMARTSYNC_ASSOCIATION_KEY,
    SMARTVAULT_TYPE_ID: SMARTVAULT_ASSOCIATION_KEY,
    SMARTCENTER_TYPE_ID: SMARTCENTER_ASSOCIATION_KEY,
}

# HubSpot dealstage ID to CRM Deal Status name (value transformation, not a field map)
DEALSTAGE_TO_STATUS: dict[str, str] = {
    # Government Sales Pipeline (1563612861)
    "2508204762": "On-Hold / Timing",
    "2508204763": "Discovery",
    "2508204764": "Solution Design",
    "2508204765": "Due Diligence",
    "2508204766": "Presentation",
    "2508204767": "Contracting",
    "2508204768": "Won",
    "2508204769": "Lost",
    # Commercial Sales Pipeline (default)
    "2464102112": "On-Hold / Timing",
    "appointmentscheduled": "Discovery",
    "qualifiedtobuy": "Solution Design",
    "presentationscheduled": "Due Diligence",
    "decisionmakerboughtin": "Presentation",
    "contractsent": "Contracting",
    "closedwon": "Won",
    "closedlost": "Lost",
    # Commercial Partner Deals (1688735440)
    "2689079009": "Discovery",
    "2689079011": "Proposal & Pricing",
    "2689079012": "RFP / Decision TBD",
    "2689079013": "Contracting",
    "2689079014": "Won",
    "2689079015": "Lost",
}

# HubSpot pipeline ID to CRM Pipeline name
PIPELINE_MAP: dict[str, str] = {
    "1563612861": "Government Sales",
    "default": "Commercial Sales",
    "1688735440": "Commercial Partner Deals",
}

# HubSpot company property to CRM Organization field
COMPANY_FIELD_MAP: dict[str, str] = {
    # To be populated when field mapping is finalized.
    # Example entries:
    # "name": "organization_name",
    # "domain": "website",
    # "numberofemployees": "no_of_employees",
    # "annualrevenue": "annual_revenue",
    # "industry": "industry",
}

# HubSpot deal property to CRM Deal field
DEAL_FIELD_MAP: dict[str, str] = {
    "dealname": "custom_hubspot_deal_name",
    "amount": "deal_value",
    "dealstage": "status",
    "pipeline": "custom_pipeline",
    "closedate": "custom_expected_close_date",
    "equipment_type": "custom_equipment_type",
    "machine_ownership_status": "custom_machine_ownership_status",
    "opportunity_term": "custom_opportunity_term",
    "hubspot_owner_id": "deal_owner",
    "client_id": "custom_client_id",
    "master_client_id": "custom_master_client_id",
}

# HubSpot contact property to Frappe Contact field
CONTACT_FIELD_MAP: dict[str, str] = {
    "firstname": "first_name",
    "lastname": "last_name",
    "email": "email",
    "mobilephone": "mobile_no",
    "phone": "phone",
    "company": "company_name",
}

# HubSpot deployment site property to Deployment Location field
SITE_FIELD_MAP: dict[str, str] = {
    "site_location_name": "location_name",
    "locale": "locale",
    "ior": "ior",
    "install_type": "install_type",
    "expedited_delivery": "expedited_delivery",
    "shipping_address": "shipping_address",
    "billing_address": "billing_address",
    "po_and_tracking": "po_and_tracking",
    "wrap_type": "wrap_type",
}

# Shared fields common to most machine types
_COMMON_MACHINE_FIELDS: dict[str, str] = {
    "machine_name": "machine_name",
    "smartscreen": "smartscreen",
    "workflow": "workflow",
    "serial_validation": "serial_validation",
    "home_screen_logo": "home_screen_logo",
    "notes": "notes",
    "power_connection": "power_connection",
    "connectivity_type": "connectivity_type",
}

_COMMON_LOCKER_FIELDS: dict[str, str] = {
    **_COMMON_MACHINE_FIELDS,
    "bin_door_type": "bin_door_type",
    "casters": "casters",
    "plug_type": "plug_type",
    "interior_lighting": "interior_lighting",
    "label_color": "label_color",
    "offline_sales": "offline_sales",
    "power_connections_in_bins": "power_connections",
    "lan_ports_in_bins": "lan_ports",
}

SMARTSTATION_FIELD_MAP: dict[str, str] = {
    **_COMMON_MACHINE_FIELDS,
    "name": "machine_name",  # SmartStation uses "name" not "machine_name"; overrides common
    "serial_validation": "serial_validaton",  # Note: typo in Frappe fieldname
    "casters": "casters",
    "machine_key": "machine_key",
    "offline_sales": "offline_sales",
    "label_color": "label_color",
    "card_reader_type": "card_reader_type",
}

SMARTLOCKER_FIELD_MAP: dict[str, str] = {
    **_COMMON_LOCKER_FIELDS,
    "n3d_printed": "3d_printed",
}

SMARTSYNC_FIELD_MAP: dict[str, str] = {
    **_COMMON_LOCKER_FIELDS,
    "n3d_printed": "3d_printed",
}

SMARTVAULT_FIELD_MAP: dict[str, str] = {
    **_COMMON_LOCKER_FIELDS,
}

SMARTCENTER_FIELD_MAP: dict[str, str] = {
    "machine_name": "machine_name",
    "smartscreen": "smartscreen",
    "workflow": "workflow",
    "serial_validation": "serial_validation",
    "home_screen_logo": "home_screen_logo",
    "notes": "notes",
    "kiosk_options": "kiosk_options",
    "kvm_switch_options": "kvm_switch_options",
    "monitor_options": "monitor_options",
    "power_connections_in_bins": "electrical_outlet_in_bins",
    "lan_ports_in_bins": "network_port_in_bins",
    "network_options": "network_options",
    "interior_lighting": "interior_kiosk_lighting",
    "bin_door_type": "locker_bin_door_type",
    "countertop_color": "countertop_color",
    "ada_side_table": "ada_side_table",
    "kiosk_side_for_table": "kiosk_side_for_table",
    "monitor_mount": "monitor_mount",
}

# Machine type ID to field map
MACHINE_FIELD_MAPS: dict[str, dict[str, str]] = {
    SMARTSTATION_TYPE_ID: SMARTSTATION_FIELD_MAP,
    SMARTLOCKER_TYPE_ID: SMARTLOCKER_FIELD_MAP,
    SMARTSYNC_TYPE_ID: SMARTSYNC_FIELD_MAP,
    SMARTVAULT_TYPE_ID: SMARTVAULT_FIELD_MAP,
    SMARTCENTER_TYPE_ID: SMARTCENTER_FIELD_MAP,
}

# HubSpot bin property to bin data keys
BIN_FIELD_MAP: dict[str, str] = {
    "bin_number": "bin_number",
    "bin_type": "bin_type",
    "size": "size",
}

# HubSpot properties to request for each machine type
MACHINE_PROPERTIES: dict[str, list[str]] = {
    type_id: list(field_map.keys())
    for type_id, field_map in MACHINE_FIELD_MAPS.items()
}

BIN_PROPERTIES = list(BIN_FIELD_MAP.keys())
