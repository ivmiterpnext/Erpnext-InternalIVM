# Frappe Patch Scripts Guide

This guide explains how to create and execute data migration patches in Frappe 16.

## Overview

Patches are Python scripts that run once during the update process to migrate data, fix inconsistencies, or make schema changes. They are essential for safely evolving your application without breaking existing installations.

## When to Use Patches

Use patches for:
- **Field renaming** with data preservation
- **Data type changes** (e.g., Data → Attach, Select → Link)
- **Data transformations** (cleaning, formatting, restructuring)
- **Bulk updates** to existing records
- **Schema migrations** that require data handling
- **Fixing data inconsistencies** from bugs or imports

## Patch Workflow

### 1. Update DocType Definition

**IMPORTANT**: Always update your DocType JSON files FIRST, before creating the patch.

```bash
# In your Frappe bench directory
cd frappe-bench

# Make changes to your DocType in the UI or directly edit the JSON files
# For example, add the new 'legacy_wrap_layout' field to your DocType

# Export the changes (if you made them in UI)
bench --site your-site.local export-doc "Project" --force
```

The order is critical:
1. Add new field (`legacy_wrap_layout`) to DocType
2. Keep old field (`wrap_layout`) temporarily
3. Create and run patch to migrate data
4. Remove old field from DocType (or change its purpose)

### 2. Create Patch File

Patches go in `apps/ivm/ivm/patches/` directory.

**Naming convention**: Use descriptive, snake_case names:
- ✅ `rename_wrap_layout_field_migration.py`
- ✅ `migrate_project_status_to_new_values.py`
- ✅ `cleanup_orphaned_client_records.py`
- ❌ `patch1.py`
- ❌ `fix.py`

**File structure**:
```python
"""
Brief description of what this patch does.

Detailed explanation of the migration strategy.
"""

from __future__ import annotations

import frappe


def execute() -> None:
	"""Main entry point - called by Frappe's patch system."""
	# Your migration code here
	pass
```

### 3. Register Patch

Add your patch to `apps/ivm/ivm/patches.txt`:

```txt
[pre_model_sync]
# Patches here run BEFORE DocType schema changes are applied
# Use for: Preparing data before schema changes

[post_model_sync]
# Patches here run AFTER DocType schema changes are applied
# Use for: Most data migrations
ivm.patches.add_hubspot_custom_fields
ivm.patches.rename_wrap_layout_field_migration  # Your new patch
```

**When to use `pre_model_sync` vs `post_model_sync`**:

- **`pre_model_sync`**: Rare usage
  - Preparing data before removing fields
  - Temporary data storage before major schema changes
  
- **`post_model_sync`** (recommended for most cases):
  - Field renames and migrations
  - Data transformations
  - Populating new fields

### 4. Test Locally

```bash
cd frappe-bench

# Run the patch on your local site
bench --site your-site.local migrate

# Check logs for any errors
tail -f sites/your-site.local/logs/bench.log

# Verify the migration in the database
bench --site your-site.local console

# In the console:
>>> frappe.db.sql("SELECT name, legacy_wrap_layout, wrap_layout FROM tabProject LIMIT 5", as_dict=True)
```

### 5. Deploy to Production

Once tested locally:

1. Commit the patch file to git
2. Push to your repository
3. Deploy to staging environment first
4. Test thoroughly on staging with production-like data
5. Deploy to production
6. Run `bench migrate` on production site

## Migration Patterns

### Pattern 1: Field Rename (Recommended)

Use Frappe's built-in `rename_field` utility:

```python
from frappe.model.utils.rename_field import rename_field

def execute() -> None:
	if frappe.db.has_column("Project", "wrap_layout"):
		rename_field("Project", "wrap_layout", "legacy_wrap_layout")
```

**Advantages**:
- Handles all edge cases
- Updates indexes and constraints
- Transaction-safe
- Maintains data integrity

### Pattern 2: SQL-Based Migration

For large datasets or custom transformations:

```python
def execute() -> None:
	batch_size = 1000
	offset = 0
	
	while True:
		records = frappe.db.sql("""
			SELECT name, old_field
			FROM `tabDocType`
			WHERE old_field IS NOT NULL
			LIMIT %s OFFSET %s
		""", (batch_size, offset), as_dict=True)
		
		if not records:
			break
		
		for record in records:
			frappe.db.set_value(
				"DocType",
				record.name,
				"new_field",
				record.old_field,
				update_modified=False
			)
		
		frappe.db.commit()
		offset += batch_size
```

**Advantages**:
- Better performance for large datasets
- More control over the process
- Can batch commits to avoid long transactions

### Pattern 3: ORM-Based Migration

For complex business logic:

```python
def execute() -> None:
	records = frappe.get_all("Project", fields=["name", "old_field"])
	
	for record in records:
		doc = frappe.get_doc("Project", record.name)
		
		# Apply business logic/transformations
		doc.new_field = transform_data(doc.old_field)
		
		# Save with flags to avoid triggers
		doc.flags.ignore_validate = True
		doc.flags.ignore_mandatory = True
		doc.save()
```

**Advantages**:
- Can use document methods
- Triggers can be controlled with flags
- Good for complex transformations

## Safety Best Practices

### 1. Idempotency

Patches should be safe to run multiple times:

```python
def execute() -> None:
	# Check if migration already completed
	if not frappe.db.has_column("Project", "old_field"):
		frappe.logger().info("Migration already completed, skipping")
		return
	
	# Or check if data already migrated
	if frappe.db.count("Project", {"new_field": ["is", "set"]}) > 0:
		frappe.logger().info("Data already migrated, skipping")
		return
	
	# Proceed with migration
	...
```

### 2. Batch Processing

For large datasets (>10,000 records):

```python
def execute() -> None:
	batch_size = 1000  # Adjust based on your dataset
	total = frappe.db.count("Project")
	processed = 0
	
	while processed < total:
		# Process batch
		...
		
		# Commit after each batch
		frappe.db.commit()
		
		# Log progress
		frappe.logger().info(f"Processed {processed}/{total} records")
		processed += batch_size
```

### 3. Error Handling

```python
def execute() -> None:
	try:
		# Migration code
		migrate_data()
		
	except Exception as e:
		# Log detailed error
		frappe.log_error(
			title="Migration Failed: Project Wrap Layout",
			message=frappe.get_traceback()
		)
		
		# Rollback any changes
		frappe.db.rollback()
		
		# Re-raise to mark patch as failed
		raise
```

### 4. Validation

Verify migration success:

```python
def execute() -> None:
	# Migrate data
	migrate_data()
	
	# Verify
	unmigrated = frappe.db.count("Project", {
		"old_field": ["is", "set"],
		"new_field": ["is", "not set"]
	})
	
	if unmigrated > 0:
		frappe.throw(f"Migration incomplete: {unmigrated} records not migrated")
```

### 5. Logging

Use proper logging for debugging:

```python
def execute() -> None:
	frappe.logger().info("Starting migration for Project.wrap_layout")
	
	# Migration code
	...
	
	frappe.logger().info(f"Migrated {count} records successfully")
```

## Performance Considerations

### For Small Datasets (<10,000 records)

- ORM-based approach is fine
- Single transaction is acceptable
- Simple error handling

### For Medium Datasets (10,000-100,000 records)

- Use SQL-based approach with batching
- Commit every 1,000-5,000 records
- Log progress regularly

### For Large Datasets (>100,000 records)

- Use raw SQL with efficient queries
- Smaller batch sizes (500-1,000)
- Consider running during low-traffic hours
- Monitor database load
- Add progress percentage logging

### Query Optimization

```python
# ❌ Bad: N+1 query pattern
for project in frappe.get_all("Project"):
	doc = frappe.get_doc("Project", project.name)  # Extra query per record
	# Process doc

# ✅ Good: Single query with needed fields
projects = frappe.get_all("Project", fields=["name", "old_field", "new_field"])
for project in projects:
	# Process project dict directly
```

## Testing Patches

### Local Testing Checklist

- [ ] Test on a fresh database with sample data
- [ ] Test on a copy of production database
- [ ] Verify data integrity after migration
- [ ] Run the patch twice to ensure idempotency
- [ ] Check database performance during migration
- [ ] Verify no foreign key violations
- [ ] Check error logs for any warnings

### Test Script Example

```bash
#!/bin/bash

# Backup database before testing
bench --site test-site.local backup --with-files

# Run migration
bench --site test-site.local migrate

# Validate results
bench --site test-site.local console << EOF
import frappe

# Count migrated records
migrated = frappe.db.count("Project", {"legacy_wrap_layout": ["is", "set"]})
print(f"Migrated records: {migrated}")

# Check for any issues
issues = frappe.db.sql("""
	SELECT name, wrap_layout, legacy_wrap_layout
	FROM tabProject
	WHERE wrap_layout IS NOT NULL AND legacy_wrap_layout IS NULL
""", as_dict=True)

if issues:
	print(f"Found {len(issues)} records with migration issues")
else:
	print("All records migrated successfully")
EOF
```

## Common Pitfalls

### 1. Running Patch Before DocType Update

**Problem**: Patch tries to write to field that doesn't exist yet.

**Solution**: Always use `post_model_sync` for most migrations.

### 2. Not Handling NULL Values

```python
# ❌ Bad
doc.new_field = doc.old_field.strip()  # Fails if old_field is None

# ✅ Good
doc.new_field = doc.old_field.strip() if doc.old_field else None
```

### 3. Forgetting update_modified Flag

```python
# ❌ Bad: Updates 'modified' timestamp on all records
frappe.db.set_value("Project", name, "new_field", value)

# ✅ Good: Preserves original modified timestamp
frappe.db.set_value("Project", name, "new_field", value, update_modified=False)
```

### 4. Not Batching Large Datasets

**Problem**: Migration times out or consumes too much memory.

**Solution**: Always batch when dealing with >10,000 records.

### 5. Ignoring Errors

```python
# ❌ Bad
try:
	migrate_record(record)
except:
	pass  # Silently ignores errors

# ✅ Good
try:
	migrate_record(record)
except Exception as e:
	frappe.log_error(f"Failed to migrate {record.name}: {str(e)}")
	failed_records.append(record.name)
```

## Debugging Failed Patches

### 1. Check Migration Status

```bash
# See which patches have been executed
bench --site your-site.local console

>>> frappe.db.sql("SELECT * FROM `tabPatch Log` ORDER BY creation DESC LIMIT 10", as_dict=True)
```

### 2. Mark Patch as Not Executed

If a patch partially failed and you want to re-run it:

```bash
bench --site your-site.local console

>>> frappe.db.sql("DELETE FROM `tabPatch Log` WHERE patch LIKE '%rename_wrap_layout%'")
>>> frappe.db.commit()
```

Then run `bench migrate` again.

### 3. Check Error Logs

```bash
# View recent error logs
bench --site your-site.local console

>>> errors = frappe.get_all("Error Log", 
...     fields=["name", "error", "creation"],
...     order_by="creation DESC",
...     limit=5)
>>> for err in errors:
...     print(f"{err.creation}: {err.error[:100]}")
```

## Example: Complete Migration Process

Here's a complete example for migrating a field type change:

### Step 1: Update DocType JSON

Add new field `legacy_wrap_layout` (Data type) to Project DocType.
Keep existing `wrap_layout` field for now.

### Step 2: Create Patch

`apps/ivm/ivm/patches/v1_0/migrate_wrap_layout.py`:

```python
"""Migrate wrap_layout field from Data to Attach type."""

from __future__ import annotations

import frappe
from frappe.model.utils.rename_field import rename_field


def execute() -> None:
	"""Rename wrap_layout to legacy_wrap_layout."""
	frappe.reload_doc("projects", "doctype", "project")
	
	if frappe.db.has_column("Project", "wrap_layout"):
		# Rename the existing field
		rename_field("Project", "wrap_layout", "legacy_wrap_layout")
		frappe.logger().info("Renamed wrap_layout to legacy_wrap_layout")
	else:
		frappe.logger().info("wrap_layout field not found, migration may have already run")
```

### Step 3: Register Patch

Update `patches.txt`:

```txt
[post_model_sync]
ivm.patches.v1_0.migrate_wrap_layout
```

### Step 4: Update DocType Again

Now add new `wrap_layout` field with Attach type.

### Step 5: Test and Deploy

```bash
# Test locally
bench --site test.local migrate

# Verify
bench --site test.local console
>>> frappe.db.get_value("Project", {"legacy_wrap_layout": ["is", "set"]}, ["name", "legacy_wrap_layout"], as_dict=True)

# Deploy
git add .
git commit -m "feat: migrate wrap_layout field to Attach type"
git push
```

## Additional Resources

- [Official Frappe Migration Guide](https://docs.frappe.io/framework/user/en/database-migrations)
- [Frappe Database API](https://frappeframework.com/docs/user/en/api/database)
- [rename_field Source Code](https://github.com/frappe/frappe/blob/version-16/frappe/model/utils/rename_field.py)

## Questions or Issues?

- Check Error Log DocType in your site
- Review `sites/your-site/logs/bench.log`
- Test patches on database copies before production
- Always backup before running migrations in production
