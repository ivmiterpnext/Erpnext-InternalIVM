"""
⚠️ TEACHING EXAMPLE ONLY - DO NOT USE DIRECTLY ⚠️

This file demonstrates three different approaches to data migration.
Use this as a reference when creating your own patches.

For actual patches, see:
- migrate_project_wrap_layout_to_legacy.py (field rename example)
- remap_select_field_options.py (select option remapping example)
- TEMPLATE_patch.py (blank template)

---

Data migration patch: Rename wrap_layout field to legacy_wrap_layout

This patch safely migrates existing data from the old 'wrap_layout' field
(Data field type) to a new 'legacy_wrap_layout' field, allowing the creation
of a new 'wrap_layout' field with Attach field type.

Migration Strategy:
1. Verify the new field structure exists in the DocType JSON
2. Use SQL to efficiently copy data from old field to new field
3. Handle batching for large datasets to avoid memory issues
4. Clear old field values after successful migration
5. Log progress and any errors for debugging

Safety Measures:
- Uses transactions with explicit commits for batch processing
- Validates data before and after migration
- Provides detailed logging of the migration process
- Handles edge cases (null values, empty strings, etc.)
"""

from __future__ import annotations

import frappe
from frappe.model.utils.rename_field import rename_field


def execute() -> None:
	"""Main execution function for the patch."""
	frappe.reload_doc("Project", "Project")  # Replace with your actual module and doctype
	
	# Option 1: Using Frappe's built-in rename_field utility (RECOMMENDED)
	# This is the safest approach as it handles all the complexity
	migrate_using_rename_field()
	
	# Option 2: Manual migration with SQL (if rename_field doesn't work)
	# Use this only if you need custom logic or the rename utility fails
	# migrate_using_sql()


def migrate_using_rename_field() -> None:
	"""
	Use Frappe's built-in rename_field utility (recommended approach).
	
	This method:
	- Updates the database column name
	- Updates all metadata references
	- Handles indexes and constraints
	- Is transaction-safe
	"""
	doctype_name = "Project"  # Replace with your DocType
	old_fieldname = "wrap_layout"
	new_fieldname = "legacy_wrap_layout"
	
	try:
		# Check if the field still exists with the old name in the database
		# This prevents errors if the patch runs multiple times
		if frappe.db.has_column(doctype_name, old_fieldname):
			frappe.logger().info(
				f"Renaming field '{old_fieldname}' to '{new_fieldname}' in {doctype_name}"
			)
			
			# Rename the field - this updates both schema and data
			rename_field(doctype_name, old_fieldname, new_fieldname)
			
			frappe.logger().info(
				f"Successfully renamed field '{old_fieldname}' to '{new_fieldname}'"
			)
		else:
			frappe.logger().info(
				f"Field '{old_fieldname}' does not exist in {doctype_name}, skipping migration"
			)
			
	except Exception as e:
		frappe.log_error(
			title=f"Field Rename Migration Failed: {doctype_name}",
			message=frappe.get_traceback(),
		)
		# Re-raise to prevent patch from being marked as successful
		raise


def migrate_using_sql() -> None:
	"""
	Manual SQL-based migration (use only if rename_field doesn't work).
	
	This approach gives you more control but requires careful handling.
	Use this when you need to:
	- Transform data during migration
	- Handle complex data mapping
	- Migrate between different field types with custom logic
	"""
	doctype_name = "Project"  # Replace with your DocType
	old_fieldname = "wrap_layout"
	new_fieldname = "legacy_wrap_layout"
	batch_size = 1000  # Process records in batches to avoid memory issues
	
	try:
		# Step 1: Check if the new field exists in the database
		if not frappe.db.has_column(doctype_name, new_fieldname):
			frappe.throw(
				f"Field '{new_fieldname}' does not exist in {doctype_name}. "
				"Please ensure the DocType JSON has been updated before running this patch."
			)
		
		# Step 2: Check if the old field exists
		if not frappe.db.has_column(doctype_name, old_fieldname):
			frappe.logger().info(
				f"Field '{old_fieldname}' does not exist, migration may have already run"
			)
			return
		
		# Step 3: Get count of records that need migration
		# Only migrate records where old field has data and new field is empty
		count_query = f"""
			SELECT COUNT(*) as count
			FROM `tab{doctype_name}`
			WHERE `{old_fieldname}` IS NOT NULL
				AND `{old_fieldname}` != ''
				AND (`{new_fieldname}` IS NULL OR `{new_fieldname}` = '')
		"""
		total_count = frappe.db.sql(count_query, as_dict=True)[0].count
		
		frappe.logger().info(
			f"Starting migration for {total_count} records in {doctype_name}"
		)
		
		if total_count == 0:
			frappe.logger().info("No records to migrate")
			return
		
		# Step 4: Batch migration for large datasets
		migrated_count = 0
		offset = 0
		
		while offset < total_count:
			# Get batch of record names
			records = frappe.db.sql(
				f"""
				SELECT name, `{old_fieldname}`
				FROM `tab{doctype_name}`
				WHERE `{old_fieldname}` IS NOT NULL
					AND `{old_fieldname}` != ''
					AND (`{new_fieldname}` IS NULL OR `{new_fieldname}` = '')
				LIMIT {batch_size} OFFSET {offset}
				""",
				as_dict=True,
			)
			
			if not records:
				break
			
			# Update records in this batch
			for record in records:
				try:
					# Copy data from old field to new field
					frappe.db.set_value(
						doctype_name,
						record.name,
						new_fieldname,
						record[old_fieldname],
						update_modified=False,  # Don't update 'modified' timestamp
					)
					migrated_count += 1
					
				except Exception as e:
					frappe.log_error(
						title=f"Migration Error for {record.name}",
						message=f"Error migrating {record.name}: {str(e)}\n{frappe.get_traceback()}",
					)
					# Continue with other records instead of failing completely
					continue
			
			# Commit after each batch to avoid long-running transactions
			frappe.db.commit()
			
			offset += batch_size
			
			# Log progress
			progress_pct = (offset / total_count) * 100
			frappe.logger().info(
				f"Migration progress: {migrated_count}/{total_count} ({progress_pct:.1f}%)"
			)
		
		# Step 5: Verify migration success
		remaining_count = frappe.db.sql(count_query, as_dict=True)[0].count
		
		if remaining_count == 0:
			frappe.logger().info(
				f"Successfully migrated {migrated_count} records. "
				f"All data copied from '{old_fieldname}' to '{new_fieldname}'"
			)
			
			# Step 6: Clear old field values (optional, but recommended)
			# This ensures no confusion about which field is authoritative
			frappe.db.sql(
				f"""
				UPDATE `tab{doctype_name}`
				SET `{old_fieldname}` = NULL
				WHERE `{new_fieldname}` IS NOT NULL
				"""
			)
			frappe.db.commit()
			
			frappe.logger().info(f"Cleared old field '{old_fieldname}' values")
		else:
			frappe.log_error(
				title=f"Incomplete Migration: {doctype_name}",
				message=f"{remaining_count} records still need migration",
			)
			
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(
			title=f"SQL Migration Failed: {doctype_name}",
			message=frappe.get_traceback(),
		)
		raise


def migrate_with_data_transformation() -> None:
	"""
	Example: Migration with data transformation.
	
	Use this pattern when you need to transform or clean data during migration.
	For example, converting URLs to file paths, formatting changes, etc.
	"""
	doctype_name = "Project"
	old_fieldname = "wrap_layout"
	new_fieldname = "legacy_wrap_layout"
	batch_size = 500
	
	# Get all records that need migration using ORM
	filters = {old_fieldname: ["is", "set"]}
	records = frappe.get_all(
		doctype_name, filters=filters, fields=["name", old_fieldname], limit_page_length=batch_size
	)
	
	total = len(records)
	processed = 0
	
	for record in records:
		try:
			# Get the actual document
			doc = frappe.get_doc(doctype_name, record.name)
			
			# Transform the data (example: clean whitespace)
			old_value = doc.get(old_fieldname)
			if old_value:
				# Apply any transformations here
				transformed_value = old_value.strip()
				
				# Set the new field value
				doc.set(new_fieldname, transformed_value)
				
				# Clear the old field
				doc.set(old_fieldname, None)
				
				# Save without triggering validations or workflow
				doc.flags.ignore_validate = True
				doc.flags.ignore_mandatory = True
				doc.save()
				
			processed += 1
			
			# Commit every 100 records
			if processed % 100 == 0:
				frappe.db.commit()
				frappe.logger().info(f"Processed {processed}/{total} records")
				
		except Exception as e:
			frappe.log_error(
				title=f"Transformation Error for {record.name}",
				message=frappe.get_traceback(),
			)
			continue
	
	frappe.db.commit()
	frappe.logger().info(f"Migration completed. Processed {processed} records.")
