"""
Constants for Deployment Location machine child tables.
There are JS equivalents in ``deployment_location.js`` and ``CRM_Deal.js``
"""

# Maps each machine child table fieldname on Deployment Location to the
# read-only quantity field that tracks its row count.
TABLE_TO_QUANTITY: dict[str, str] = {
    "smartstation_details": "number_of_machines",
    "smartlocker_details": "number_of_primary_lockers",
    "smartsync_details": "number_of_secondary_lockers",
    "smartcenter_details": "number_of_kiosks",
    "smartvault_details": "number_of_vaults",
}

# Maps each child table fieldname to its DocType name.
TABLE_TO_DOCTYPE: dict[str, str] = {
    "smartstation_details": "Deployment SmartStation Details",
    "smartlocker_details": "Deployment SmartLocker Details",
    "smartsync_details": "Deployment SmartSync Details",
    "smartvault_details": "Deployment SmartVault Details",
    "smartcenter_details": "Deployment SmartCenter Details",
}

# Human-readable labels for error messages, keyed by child table fieldname.
TABLE_LABELS: dict[str, str] = {
    "smartstation_details": "SmartStation",
    "smartlocker_details": "SmartLocker",
    "smartsync_details": "SmartSync",
    "smartcenter_details": "SmartCenter",
    "smartvault_details": "SmartVault",
}

# Convenience list of all machine child table fieldnames.
MACHINE_DETAIL_TABLES: list[str] = list(TABLE_TO_QUANTITY.keys())

# Frappe internal metadata fields to exclude when copying child table rows.
SKIP_CHILD_FIELDS: frozenset[str] = frozenset({
    "name", "owner", "creation", "modified", "modified_by",
    "parent", "parentfield", "parenttype", "idx", "docstatus", "doctype",
})
