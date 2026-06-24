"""
Shared constants for the HubSpot integration package.
"""

from ivm.deals.constants import TABLE_TO_DOCTYPE

# Service account for all HubSpot-initiated writes.
HUBSPOT_USER = "hubspot@ivm.local"
HUBSPOT_ROLE = "Integration"

# Custom fields used for dedup/lookup across handlers.
HUBSPOT_DEAL_ID_FIELD = "custom_hubspot_deal_id"
HUBSPOT_CONTACT_ID_FIELD = "custom_hubspot_contact_id"
HUBSPOT_COMPANY_ID_FIELD = "custom_hubspot_company_id"

DEAL_TYPE_ID = "0-3"
CONTACT_TYPE_ID = "0-1"
COMPANY_TYPE_ID = "0-2"

# Engagement object type IDs (per HubSpot docs: understanding-the-crm#object-type-ids)
CALL_TYPE_ID = "0-48"
NOTE_TYPE_ID = "0-46"
EMAIL_TYPE_ID = "0-49"
TASK_TYPE_ID = "0-27"
MEETING_TYPE_ID = "0-47"

# Maps engagement objectTypeId → engagement type name (used in API paths).
ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID: dict[str, str] = {
    CALL_TYPE_ID: "calls",
    NOTE_TYPE_ID: "notes",
    EMAIL_TYPE_ID: "emails",
    TASK_TYPE_ID: "tasks",
    MEETING_TYPE_ID: "meetings",
}

DEPLOYMENT_SITE_TYPE_ID = "2-226377266"
SMARTSTATION_TYPE_ID = "2-230236986"
SMARTLOCKER_TYPE_ID = "2-230363982"
SMARTSYNC_TYPE_ID = "2-230364924"
SMARTVAULT_TYPE_ID = "2-230365132"
SMARTCENTER_TYPE_ID = "2-230365088"
BIN_TYPE_ID = "2-230364465"

# HubSpot association key suffixes (prefixed with p{portal_id}_)
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

# Maps HubSpot custom object type ID to child table fieldname on Deployment Location.
MACHINE_TYPE_TO_CHILD_TABLE: dict[str, str] = {
    SMARTSTATION_TYPE_ID: "smartstation_details",
    SMARTLOCKER_TYPE_ID: "smartlocker_details",
    SMARTSYNC_TYPE_ID: "smartsync_details",
    SMARTVAULT_TYPE_ID: "smartvault_details",
    SMARTCENTER_TYPE_ID: "smartcenter_details",
}

# Maps HubSpot custom object type ID to child table DocType name.
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

# Maps HubSpot industry enum keys to existing CRM Industry record names.
# Only keys that match a record already in the CRM Industry doctype are listed.
# Unmapped keys will be silently skipped (no industry set on the org).
HUBSPOT_INDUSTRY_LABELS: dict[str, str] = {
    "ACCOUNTING": "Accounting",
    "AIRLINES_AVIATION": "Airline",
    "AVIATION_AEROSPACE": "Aerospace",
    "AUTOMOTIVE": "Automotive",
    "BANKING": "Banking",
    "BIOTECHNOLOGY": "Biotechnology",
    "BROADCAST_MEDIA": "Broadcasting",
    "CAPITAL_MARKETS": "Brokerage",
    "CHEMICALS": "Chemical",
    "COMPUTER_HARDWARE": "Computer",
    "COMPUTER_NETWORKING": "Computer",
    "COMPUTER_SOFTWARE": "Software",
    "INTERNET": "Internet Publishing",
    "CONSUMER_GOODS": "Consumer Products",
    "COSMETICS": "Cosmetics",
    "DEFENSE_SPACE": "Defense",
    "EDUCATION_MANAGEMENT": "Education",
    "HIGHER_EDUCATION": "Education",
    "PRIMARY_SECONDARY_EDUCATION": "Education",
    "CONSUMER_ELECTRONICS": "Electronics",
    "ELECTRICAL_ELECTRONIC_MANUFACTURING": "Electronics",
    "OIL_ENERGY": "Energy",
    "UTILITIES": "Energy",
    "ENTERTAINMENT": "Entertainment & Leisure, Executive Search",
    "FINANCIAL_SERVICES": "Financial Services",
    "FOOD_BEVERAGES": "Food",
    "FOOD_PRODUCTION": "Food",
    "DAIRY": "Food",
    "SUPERMARKETS": "Grocery",
    "HOSPITAL_HEALTH_CARE": "Health Care",
    "HEALTH_WELLNESS_AND_FITNESS": "Health Care",
    "INVESTMENT_BANKING": "Investment Banking",
    "LAW_PRACTICE": "Legal",
    "LEGAL_SERVICES": "Legal",
    "INDUSTRIAL_AUTOMATION": "Manufacturing",
    "MACHINERY": "Manufacturing",
    "MOTION_PICTURES_AND_FILM": "Motion Picture & Video",
    "MUSIC": "Music",
    "NEWSPAPERS": "Newspaper Publishers",
    "PHARMACEUTICALS": "Pharmaceuticals",
    "VENTURE_CAPITAL_PRIVATE_EQUITY": "Private Equity",
    "PUBLISHING": "Publishing",
    "REAL_ESTATE": "Real Estate",
    "COMMERCIAL_REAL_ESTATE": "Real Estate",
    "RETAIL": "Retail & Wholesale",
    "WHOLESALE": "Retail & Wholesale",
    "STAFFING_AND_RECRUITING": "Service",
    "CONSUMER_SERVICES": "Service",
    "SPORTS": "Sports",
    "INFORMATION_TECHNOLOGY_AND_SERVICES": "Technology",
    "INFORMATION_SERVICES": "Technology",
    "TELECOMMUNICATIONS": "Telecommunications",
    "WIRELESS": "Telecommunications",
    "TRANSPORTATION_TRUCKING_RAILROAD": "Transportation",
    "LOGISTICS_AND_SUPPLY_CHAIN": "Transportation",
}

# HubSpot company property to CRM Organization field
COMPANY_FIELD_MAP: dict[str, str] = {
    "website": "website",
    "annualrevenue": "annual_revenue",
    "industry": "industry",
    "numberofemployees": "no_of_employees",
    "hs_lead_status": "custom_lead_status",
    "lifecyclestage": "custom_lifecycle_stage",
    "type": "custom_company_type",
    "description": "custom_description",
    "phone": "custom_phone",
    "timezone": "custom_timezone",
    "hs_logo_url": "organization_logo",
}

# HubSpot company address properties fetched separately from the field map
# and used to create/update an Address doc linked to the CRM Organization.
COMPANY_ADDRESS_PROPERTIES: list[str] = [
    "address", "city", "state", "country", "zip",
]

# HubSpot deal property to CRM Deal field
DEAL_FIELD_MAP: dict[str, str] = {
    "dealname": "custom_hubspot_deal_name",
    "amount": "deal_value",
    "dealstage": "status",
    "pipeline": "custom_pipeline",
    "closedate": "custom_expected_close_date",
    "dealtype": "custom_deal_type",
    "equipment_type": "custom_equipment_type",
    "machine_ownership_status": "custom_machine_ownership_status",
    "opportunity_term": "custom_opportunity_term",
    "hubspot_owner_id": "deal_owner",
    "client_id": "custom_client_id",
    "master_client_id": "custom_master_client_id",
}

# HubSpot dealtype enum key → human-readable label stored in custom_deal_type
HUBSPOT_DEAL_TYPE_LABELS: dict[str, str] = {
    "newbusiness": "New Business",
    "existingbusiness": "Existing Business",
}

# HubSpot contact property to Frappe Contact field
CONTACT_FIELD_MAP: dict[str, str] = {
    "firstname": "first_name",
    "lastname": "last_name",
    "email": "email",
    "mobilephone": "mobile_no",
    "phone": "phone",
    "company": "company_name",
    "salutation": "salutation",
    "jobtitle": "designation",
    "linkedin_account": "custom_linkedin_account",
    "lead_source": "custom_lead_source",
    "prospect_category": "custom_prospect_category",
    "hs_timezone": "custom_timezone",
    "hs_state_code": "custom_state_code",
    "hs_role": "custom_role",
}

# HubSpot contact address properties fetched separately from the field map
# and used to create/update an Address doc linked to the Contact.
CONTACT_ADDRESS_PROPERTIES: list[str] = [
    "address", "city", "state", "country",
]

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


# Custom field on FCRM Note, CRM Task, and CRM Call Log for dedup during activity sync.
HUBSPOT_ENGAGEMENT_ID_FIELD = "custom_hubspot_engagement_id"

# HubSpot CRM v3 object type names for engagements.
ENGAGEMENT_TYPE_NOTES = "notes"
ENGAGEMENT_TYPE_CALLS = "calls"
ENGAGEMENT_TYPE_EMAILS = "emails"
ENGAGEMENT_TYPE_TASKS = "tasks"
ENGAGEMENT_TYPE_MEETINGS = "meetings"

ALL_ENGAGEMENT_TYPES: list[str] = [
    ENGAGEMENT_TYPE_NOTES,
    ENGAGEMENT_TYPE_CALLS,
    ENGAGEMENT_TYPE_EMAILS,
    ENGAGEMENT_TYPE_TASKS,
    ENGAGEMENT_TYPE_MEETINGS,
]

# Properties to request from HubSpot for each engagement type.
NOTE_PROPERTIES: list[str] = [
    "hs_note_body",
    "hs_timestamp",
    "hubspot_owner_id",
    "hs_attachment_ids",
]

CALL_PROPERTIES: list[str] = [
    "hs_call_title",
    "hs_call_body",
    "hs_call_direction",
    "hs_call_duration",
    "hs_call_from_number",
    "hs_call_to_number",
    "hs_call_recording_url",
    "hs_call_status",
    "hs_timestamp",
    "hubspot_owner_id",
    "hs_attachment_ids",
]

EMAIL_PROPERTIES: list[str] = [
    "hs_email_subject",
    "hs_email_text",
    "hs_email_html",
    "hs_email_sender_email",
    "hs_email_from_email",    # actual From: address (populated for inbound emails)
    "hs_email_to_email",
    "hs_email_cc_email",
    "hs_email_bcc_email",
    "hs_email_direction",
    "hs_email_status",
    "hs_timestamp",
    "hubspot_owner_id",
    "hs_attachment_ids",
]

TASK_PROPERTIES: list[str] = [
    "hs_task_subject",
    "hs_task_body",
    "hs_task_status",
    "hs_task_priority",
    "hs_timestamp",
    "hubspot_owner_id",
    "hs_attachment_ids",
]

MEETING_PROPERTIES: list[str] = [
    "hs_meeting_title",
    "hs_meeting_body",
    "hs_meeting_start_time",
    "hs_meeting_end_time",
    "hs_timestamp",
    "hubspot_owner_id",
    "hs_attachment_ids",
]

# Maps engagement type → list of properties to request.
ENGAGEMENT_PROPERTIES: dict[str, list[str]] = {
    ENGAGEMENT_TYPE_NOTES: NOTE_PROPERTIES,
    ENGAGEMENT_TYPE_CALLS: CALL_PROPERTIES,
    ENGAGEMENT_TYPE_EMAILS: EMAIL_PROPERTIES,
    ENGAGEMENT_TYPE_TASKS: TASK_PROPERTIES,
    ENGAGEMENT_TYPE_MEETINGS: MEETING_PROPERTIES,
}

# HubSpot call direction values → CRM Call Log type.
CALL_DIRECTION_MAP: dict[str, str] = {
    "INBOUND": "Incoming",
    "OUTBOUND": "Outgoing",
}

# HubSpot call status → CRM Call Log status.
CALL_STATUS_MAP: dict[str, str] = {
    "BUSY": "Busy",
    "CALLING_CRM_USER": "Initiated",
    "CANCELED": "Canceled",
    "COMPLETED": "Completed",
    "CONNECTING": "Ringing",
    "FAILED": "Failed",
    "IN_PROGRESS": "In Progress",
    "NO_ANSWER": "No Answer",
    "QUEUED": "Queued",
    "RINGING": "Ringing",
}

# HubSpot task status → CRM Task status.
TASK_STATUS_MAP: dict[str, str] = {
    "NOT_STARTED": "Todo",
    "IN_PROGRESS": "In Progress",
    "WAITING": "Todo",
    "DEFERRED": "Backlog",
    "COMPLETED": "Done",
}

# HubSpot task priority → CRM Task priority.
TASK_PRIORITY_MAP: dict[str, str] = {
    "NONE": "Low",
    "LOW": "Low",
    "MEDIUM": "Medium",
    "HIGH": "High",
}
