"""
Migrate Project wrap_layout field from Data/Text to Attach field type.

SIMPLE APPROACH - NO PRE-EXISTING FIELD NEEDED!
================================================

This patch uses Frappe's rename_field() which:
1. Renames the database column: custom_wrap_layout → custom_legacy_wrap_layout
2. Updates all metadata automatically
3. Preserves all existing data

After this patch runs, the field custom_wrap_layout will no longer exist in
the database. You then need to:
1. Update your Project custom fields JSON to rename the field definition
2. Add a NEW custom_wrap_layout field with Attach type
3. Run bench migrate again to apply the schema changes


Use this patch if you need to preserve existing data.

Author: [Your Name]
Date: 2026-03-05
"""

from __future__ import annotations

import frappe
from frappe.model.utils.rename_field import rename_field


def execute() -> None:
	"""
	Rename custom_wrap_layout to custom_legacy_wrap_layout in Project DocType.
	
	⚠️ IMPORTANT: Customize the field names below for your actual use case!
	
	This uses Frappe's built-in rename_field utility which:
	- Renames the database column
	- Updates all metadata
	- Preserves all data
	- Is transaction-safe
	"""
	doctype_name = "Project"
	old_fieldname = "custom_wrap_layout"  # ⚠️ CHANGE THIS to your actual old field name
	new_fieldname = "custom_legacy_wrap_layout"  # ⚠️ CHANGE THIS to what you want to rename it to
	
	try:
		# Reload the DocType to get latest schema
		frappe.reload_doc("projects", "doctype", "project")
		
		# Check if the old field still exists
		if not frappe.db.has_column(doctype_name, old_fieldname):
			frappe.logger().info(
				f"Field '{old_fieldname}' does not exist in {doctype_name}. "
				"Migration may have already run, or field was removed. Skipping."
			)
			return
		
		# Check if target field already exists
		if frappe.db.has_column(doctype_name, new_fieldname):
			# Check if new field has data - if yes, migration likely already done
			has_data = frappe.db.sql(
				f"""
				SELECT COUNT(*) as count
				FROM `tab{doctype_name}`
				WHERE `{new_fieldname}` IS NOT NULL
				AND `{new_fieldname}` != ''
				""",
				as_dict=True,
			)[0].count
			
			if has_data > 0:
				frappe.logger().info(
					f"Field '{new_fieldname}' already has data. "
					"Migration appears to have already run. Skipping."
				)
				return
		
		# Get count of records that will be affected
		affected_count = frappe.db.sql(
			f"""
			SELECT COUNT(*) as count
			FROM `tab{doctype_name}`
			WHERE `{old_fieldname}` IS NOT NULL
			AND `{old_fieldname}` != ''
			""",
			as_dict=True,
		)[0].count
		
		frappe.logger().info(
			f"Starting field rename: {old_fieldname} → {new_fieldname} "
			f"in {doctype_name} ({affected_count} records with data)"
		)
		
		# Perform the rename using Frappe's utility
		# This handles:
		# - Column rename in database
		# - Index updates
		# - Constraint updates
		# - Data preservation
		rename_field(doctype_name, old_fieldname, new_fieldname)
		
		# Verify the migration
		verify_migration(doctype_name, old_fieldname, new_fieldname, affected_count)
		
		frappe.logger().info(
			f"Successfully renamed field '{old_fieldname}' to '{new_fieldname}' "
			f"in {doctype_name}"
		)
		
	except Exception as e:
		# Log detailed error for debugging
		frappe.log_error(
			title=f"Field Rename Failed: {doctype_name}.{old_fieldname}",
			message=f"Error: {str(e)}\n\n{frappe.get_traceback()}",
		)
		
		# Rollback any partial changes
		frappe.db.rollback()
		
		# Re-raise to mark patch as failed
		raise


def verify_migration(
	doctype_name: str, old_fieldname: str, new_fieldname: str, expected_count: int
) -> None:
	"""
	Verify that the migration completed successfully.
	
	Args:
		doctype_name: Name of the DocType
		old_fieldname: Original field name
		new_fieldname: New field name
		expected_count: Number of records that should have been migrated
	
	Raises:
		Exception: If verification fails
	"""
	# Check that old field no longer exists
	if frappe.db.has_column(doctype_name, old_fieldname):
		frappe.throw(
			f"Migration verification failed: Old field '{old_fieldname}' still exists"
		)
	
	# Check that new field exists
	if not frappe.db.has_column(doctype_name, new_fieldname):
		frappe.throw(
			f"Migration verification failed: New field '{new_fieldname}' does not exist"
		)
	
	# Verify data was preserved
	migrated_count = frappe.db.sql(
		f"""
		SELECT COUNT(*) as count
		FROM `tab{doctype_name}`
		WHERE `{new_fieldname}` IS NOT NULL
		AND `{new_fieldname}` != ''
		""",
		as_dict=True,
	)[0].count
	
	if migrated_count != expected_count:
		frappe.log_error(
			title=f"Migration Data Mismatch: {doctype_name}",
			message=f"Expected {expected_count} records, but found {migrated_count} "
			f"with data in '{new_fieldname}' field",
		)
		frappe.throw(
			f"Migration verification failed: Data count mismatch "
			f"(expected {expected_count}, got {migrated_count})"
		)
	
	frappe.logger().info(
		f"Migration verification passed: {migrated_count} records migrated successfully"
	)


# Alternative implementation using SQL (if rename_field doesn't work)
# Uncomment and use this if the above approach has issues

"""
def execute() -> None:
	doctype_name = "Project"
	old_fieldname = "custom_wrap_layout"
	new_fieldname = "legacy_wrap_layout"
	
	try:
		frappe.reload_doc("projects", "doctype", "project")
		
		# Check if migration needed
		if not frappe.db.has_column(doctype_name, old_fieldname):
			frappe.logger().info("Old field doesn't exist, skipping")
			return
		
		if not frappe.db.has_column(doctype_name, new_fieldname):
			frappe.throw(
				f"Target field '{new_fieldname}' does not exist. "
				"Please add it to the DocType before running this patch."
			)
		
		# Copy data from old to new field
		frappe.db.sql(f'''
			UPDATE `tab{doctype_name}`
			SET `{new_fieldname}` = `{old_fieldname}`
			WHERE `{old_fieldname}` IS NOT NULL
			AND `{old_fieldname}` != ''
			AND (`{new_fieldname}` IS NULL OR `{new_fieldname}` = '')
		''')
		frappe.db.commit()
		
		# Verify migration
		affected = frappe.db.sql(f'''
			SELECT COUNT(*) as count
			FROM `tab{doctype_name}`
			WHERE `{new_fieldname}` IS NOT NULL
		''', as_dict=True)[0].count
		
		frappe.logger().info(
			f"Copied {affected} records from {old_fieldname} to {new_fieldname}"
		)
		
		# Clear old field
		frappe.db.sql(f'''
			UPDATE `tab{doctype_name}`
			SET `{old_fieldname}` = NULL
		''')
		frappe.db.commit()
		
	except Exception as e:
		frappe.log_error(
			title=f"SQL Migration Failed: {doctype_name}",
			message=frappe.get_traceback()
		)
		frappe.db.rollback()
		raise
"""
