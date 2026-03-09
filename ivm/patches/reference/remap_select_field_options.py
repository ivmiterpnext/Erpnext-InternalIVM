"""
Remap removed Select field options to new values.

SCENARIO:
=========
You have a Select field with options: ["Option A", "Option B", "Option C"]
You want to remove "Option B" from the DocType, but existing records use it.
This patch remaps all records using "Option B" to "Option A" (or whatever you choose).

PROCESS:
========
1. Define your mapping: old_value → new_value
2. Run this patch to update existing records
3. Update your DocType JSON to remove the old options
4. Deploy and run bench migrate

Example: Project Status field
Old options: Draft, Active, On Hold, Cancelled, Completed
Removing: On Hold
Remap "On Hold" → "Active"

Author: [Your Name]
Date: 2026-03-05
"""

from __future__ import annotations

import frappe


def execute() -> None:
	"""
	Remap Select field values before removing options from DocType.
	
	This prevents data loss and validation errors when Select options are removed.
	"""
	
	# Example 1: Simple remapping for one DocType
	remap_single_field(
		doctype="Project",
		fieldname="custom_deployment_type",  # Change to your field
		mapping={
			"Old Option 1": "New Option 1",
			"Old Option 2": "New Option 2",
			"Deprecated Value": "Current Value",
		},
	)
	
	# Example 2: Multiple fields in same DocType
	# remap_multiple_fields(
	#     doctype="Client",
	#     field_mappings={
	#         "status": {
	#             "Inactive": "Active",
	#             "Suspended": "On Hold",
	#         },
	#         "type": {
	#             "Legacy": "Standard",
	#         },
	#     },
	# )
	
	# Example 3: Same remapping across multiple DocTypes
	# remap_across_doctypes(
	#     field_mappings={
	#         "Machine": {
	#             "status": {"Old Status": "New Status"}
	#         },
	#         "Board": {
	#             "status": {"Old Status": "New Status"}
	#         },
	#     }
	# )


def remap_single_field(
	doctype: str,
	fieldname: str,
	mapping: dict[str, str],
) -> None:
	"""
	Remap values for a single Select field.
	
	Args:
		doctype: Name of the DocType
		fieldname: Name of the Select field
		mapping: Dictionary mapping old values to new values
	
	Example:
		remap_single_field(
			"Project",
			"status",
			{"On Hold": "Active", "Pending": "Open"}
		)
	"""
	if not mapping:
		frappe.logger().info(f"No mapping provided for {doctype}.{fieldname}, skipping")
		return
	
	frappe.logger().info(
		f"Starting option remapping for {doctype}.{fieldname}: {mapping}"
	)
	
	total_updated = 0
	
	for old_value, new_value in mapping.items():
		# Check if any records use this old value
		count = frappe.db.count(doctype, {fieldname: old_value})
		
		if count == 0:
			frappe.logger().info(
				f"No records found with {fieldname}='{old_value}', skipping"
			)
			continue
		
		frappe.logger().info(
			f"Remapping {count} records: '{old_value}' → '{new_value}'"
		)
		
		try:
			# Update all records with this old value
			frappe.db.sql(
				f"""
				UPDATE `tab{doctype}`
				SET `{fieldname}` = %s
				WHERE `{fieldname}` = %s
				""",
				(new_value, old_value),
			)
			
			total_updated += count
			
		except Exception as e:
			frappe.log_error(
				title=f"Remapping Failed: {doctype}.{fieldname}",
				message=f"Failed to remap '{old_value}' → '{new_value}'\n{str(e)}",
			)
			raise
	
	# Commit all changes
	frappe.db.commit()
	
	# Verify the remapping
	verify_remapping(doctype, fieldname, list(mapping.keys()))
	
	frappe.logger().info(
		f"Successfully remapped {total_updated} records in {doctype}.{fieldname}"
	)


def remap_multiple_fields(
	doctype: str,
	field_mappings: dict[str, dict[str, str]],
) -> None:
	"""
	Remap values for multiple Select fields in the same DocType.
	
	Args:
		doctype: Name of the DocType
		field_mappings: Dictionary of fieldname → {old_value: new_value}
	
	Example:
		remap_multiple_fields(
			"Project",
			{
				"status": {"On Hold": "Active"},
				"priority": {"Urgent": "High"},
			}
		)
	"""
	for fieldname, mapping in field_mappings.items():
		remap_single_field(doctype, fieldname, mapping)


def remap_across_doctypes(
	field_mappings: dict[str, dict[str, dict[str, str]]],
) -> None:
	"""
	Remap values across multiple DocTypes.
	
	Args:
		field_mappings: Dictionary of doctype → fieldname → {old: new}
	
	Example:
		remap_across_doctypes({
			"Project": {
				"status": {"On Hold": "Active"}
			},
			"Task": {
				"status": {"On Hold": "Open"}
			},
		})
	"""
	for doctype, fields in field_mappings.items():
		remap_multiple_fields(doctype, fields)


def verify_remapping(
	doctype: str,
	fieldname: str,
	old_values: list[str],
) -> None:
	"""
	Verify that no records still have the old values.
	
	Args:
		doctype: Name of the DocType
		fieldname: Name of the field
		old_values: List of old values that should no longer exist
	
	Raises:
		Exception: If any records still have old values
	"""
	for old_value in old_values:
		remaining = frappe.db.count(doctype, {fieldname: old_value})
		
		if remaining > 0:
			error_msg = (
				f"Remapping verification failed: {remaining} records in "
				f"{doctype} still have {fieldname}='{old_value}'"
			)
			frappe.log_error(
				title=f"Remapping Incomplete: {doctype}.{fieldname}",
				message=error_msg,
			)
			frappe.throw(error_msg)


def remap_with_conditions(
	doctype: str,
	fieldname: str,
	mapping: dict[str, str],
	additional_filters: dict | None = None,
) -> None:
	"""
	Remap values with additional filtering conditions.
	
	Useful when you only want to remap specific records, not all records
	with the old value.
	
	Args:
		doctype: Name of the DocType
		fieldname: Name of the Select field
		mapping: Dictionary mapping old values to new values
		additional_filters: Additional filters to apply (e.g., date range)
	
	Example:
		# Only remap old projects, not new ones
		remap_with_conditions(
			"Project",
			"status",
			{"Pending": "Open"},
			{"creation": ["<", "2025-01-01"]}
		)
	"""
	for old_value, new_value in mapping.items():
		# Build filters
		filters = {fieldname: old_value}
		if additional_filters:
			filters.update(additional_filters)
		
		# Get matching records
		records = frappe.get_all(doctype, filters=filters, pluck="name")
		
		if not records:
			frappe.logger().info(f"No records match filters for {old_value}")
			continue
		
		frappe.logger().info(
			f"Remapping {len(records)} records with additional filters"
		)
		
		# Update in batches
		batch_size = 1000
		for i in range(0, len(records), batch_size):
			batch = records[i : i + batch_size]
			
			frappe.db.sql(
				f"""
				UPDATE `tab{doctype}`
				SET `{fieldname}` = %s
				WHERE `name` IN ({','.join(['%s'] * len(batch))})
				""",
				(new_value, *batch),
			)
			
			frappe.db.commit()


def log_values_before_remapping(doctype: str, fieldname: str) -> None:
	"""
	Log all current values and their counts before remapping.
	
	Useful for creating an audit trail and verifying the migration.
	
	Args:
		doctype: Name of the DocType
		fieldname: Name of the field
	"""
	values = frappe.db.sql(
		f"""
		SELECT `{fieldname}`, COUNT(*) as count
		FROM `tab{doctype}`
		WHERE `{fieldname}` IS NOT NULL
		GROUP BY `{fieldname}`
		ORDER BY count DESC
		""",
		as_dict=True,
	)
	
	frappe.logger().info(f"Current values in {doctype}.{fieldname}:")
	for row in values:
		frappe.logger().info(f"  '{row[fieldname]}': {row['count']} records")
	
	return values


# EXAMPLE USAGE FOR YOUR SPECIFIC CASE:
# ======================================

"""
# For a deployment_type field where you want to remove "Legacy" option:

def execute() -> None:
	# Optional: Log current state
	log_values_before_remapping("Project", "custom_deployment_type")
	
	# Remap the values
	remap_single_field(
		doctype="Project",
		fieldname="custom_deployment_type",
		mapping={
			"Legacy Type A": "Standard",
			"Legacy Type B": "Enterprise",
			"Deprecated Option": "Current Option",
		},
	)
	
	# Optional: Verify no records still use old values
	verify_remapping(
		"Project",
		"custom_deployment_type",
		["Legacy Type A", "Legacy Type B", "Deprecated Option"]
	)
"""
