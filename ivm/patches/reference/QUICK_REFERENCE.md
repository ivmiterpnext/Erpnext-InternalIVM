# Frappe Patch Quick Reference

## Quick Start

### 1. Create Patch File
```bash
cd apps/ivm/ivm/patches
touch my_migration_patch.py
```

### 2. Basic Patch Structure
```python
from __future__ import annotations
import frappe

def execute() -> None:
	"""Main entry point."""
	# Your code here
	pass
```

### 3. Register Patch
Edit `patches.txt`:
```txt
[post_model_sync]
ivm.patches.my_migration_patch
```

### 4. Run Migration
```bash
bench --site your-site.local migrate
```

---

## Common Operations

### Rename Field
```python
from frappe.model.utils.rename_field import rename_field

rename_field("DocType Name", "old_field", "new_field")
```

### Copy Data Between Fields
```python
frappe.db.sql("""
	UPDATE `tabDocType`
	SET new_field = old_field
	WHERE old_field IS NOT NULL
""")
frappe.db.commit()
```

### Batch Update (Large Datasets)
```python
batch_size = 1000
offset = 0

while True:
	records = frappe.db.sql("""
		SELECT name FROM `tabDocType`
		LIMIT %s OFFSET %s
	""", (batch_size, offset), as_dict=True)
	
	if not records:
		break
	
	for record in records:
		# Process record
		pass
	
	frappe.db.commit()
	offset += batch_size
```

### Update Single Value
```python
frappe.db.set_value(
	"DocType",
	"record_name",
	"fieldname",
	"new_value",
	update_modified=False  # Don't update timestamp
)
```

### Update with ORM
```python
doc = frappe.get_doc("DocType", "record_name")
doc.fieldname = "new_value"
doc.flags.ignore_validate = True
doc.save()
```

---

## Idempotency Checks

### Check if Field Exists
```python
if not frappe.db.has_column("DocType", "field_name"):
	frappe.logger().info("Field doesn't exist, skipping")
	return
```

### Check if Data Migrated
```python
count = frappe.db.count("DocType", {
	"new_field": ["is", "set"]
})

if count > 0:
	frappe.logger().info("Already migrated, skipping")
	return
```

### Check Patch Log
```python
from frappe.modules.patch_handler import executed

if executed("ivm.patches.my_patch"):
	return
```

---

## Error Handling

### Basic Try-Catch
```python
try:
	# Migration code
	migrate_data()
except Exception as e:
	frappe.log_error(
		title="Migration Failed",
		message=frappe.get_traceback()
	)
	frappe.db.rollback()
	raise
```

### Continue on Error (Per Record)
```python
failed = []
for record in records:
	try:
		process_record(record)
	except Exception as e:
		failed.append(record.name)
		frappe.log_error(f"Failed: {record.name}")
		continue

if failed:
	frappe.logger().warning(f"Failed records: {len(failed)}")
```

---

## Logging

### Info Messages
```python
frappe.logger().info("Migration started")
frappe.logger().info(f"Processed {count} records")
```

### Progress Logging
```python
progress = (processed / total) * 100
frappe.logger().info(f"Progress: {progress:.1f}% ({processed}/{total})")
```

### Error Logging
```python
frappe.log_error(
	title="Migration Error",
	message=f"Failed to process {record.name}\n{frappe.get_traceback()}"
)
```

---

## Testing Commands

### Backup Before Testing
```bash
bench --site test.local backup --with-files
```

### Run Migration
```bash
bench --site test.local migrate
```

### Check Patch Status
```bash
bench --site test.local console
>>> frappe.db.sql("SELECT * FROM `tabPatch Log` WHERE patch LIKE '%my_patch%'", as_dict=True)
```

### Re-run Patch (Testing Only)
```bash
bench --site test.local console
>>> frappe.db.sql("DELETE FROM `tabPatch Log` WHERE patch LIKE '%my_patch%'")
>>> frappe.db.commit()
>>> exit()

bench --site test.local migrate
```

### Verify Data
```bash
bench --site test.local console
>>> frappe.db.sql("SELECT name, field1, field2 FROM `tabDocType` LIMIT 5", as_dict=True)
```

---

## Performance Tips

### Dataset Size Guidelines

| Records | Approach | Batch Size | Commit Frequency |
|---------|----------|------------|------------------|
| < 10K   | ORM      | N/A        | Single commit    |
| 10K-100K| SQL      | 1000-5000  | Per batch        |
| > 100K  | Raw SQL  | 500-1000   | Per batch        |

### Efficient Query
```python
# ❌ N+1 Queries
for name in names:
	doc = frappe.get_doc("DocType", name)  # Extra query!

# ✅ Single Query
records = frappe.get_all("DocType", 
	fields=["name", "field1", "field2"])
for record in records:
	# Use record dict
```

### Index Check
```python
# Add index for better performance (if needed)
frappe.db.sql("""
	CREATE INDEX IF NOT EXISTS idx_field
	ON `tabDocType` (field_name)
""")
```

---

## Common Field Type Migrations

### Data → Attach
1. Add new Attach field with different name
2. Keep old Data field temporarily
3. Run patch (no data transformation needed)
4. Old field now renamed to legacy_*
5. New Attach field has same name

### Select → Link
1. Create new DocType for options
2. Populate new DocType with old select values
3. Add Link field
4. Patch: Map old values to new DocType names
5. Remove old Select field

### Small Text → Text Editor (HTML)
```python
# May need to escape HTML entities
import html
doc.new_field = html.escape(doc.old_field)
```

---

## Debugging

### View Recent Errors
```python
errors = frappe.get_all("Error Log",
	fields=["name", "error", "creation"],
	order_by="creation DESC",
	limit=5)
```

### Check Column Type
```python
desc = frappe.db.sql("""
	DESCRIBE `tabDocType`
""", as_dict=True)
```

### Count Records by Condition
```python
frappe.db.count("DocType", {
	"field": ["is", "set"]
})
```

---

## Pre vs Post Model Sync

### pre_model_sync
- Runs BEFORE schema changes
- Use when: Need to preserve data before field removal
- Rare usage

### post_model_sync (Recommended)
- Runs AFTER schema changes
- Use when: Migrating to new fields
- Most common use case

---

## Safety Checklist

Before deploying:
- [ ] Tested on local database copy
- [ ] Tested on production database copy
- [ ] Patch is idempotent (can run multiple times)
- [ ] Batching implemented for large datasets
- [ ] Error handling and logging in place
- [ ] Validation checks after migration
- [ ] Backup strategy confirmed
- [ ] Rollback plan documented

---

## Emergency Rollback

If patch causes issues in production:

### 1. Restore from Backup
```bash
bench --site site.local restore path/to/backup.sql.gz
```

### 2. Mark Patch as Executed (Skip)
```bash
bench --site site.local console
>>> frappe.get_doc({
...     "doctype": "Patch Log",
...     "patch": "ivm.patches.problematic_patch"
... }).insert()
>>> frappe.db.commit()
```

### 3. Fix and Redeploy
- Fix patch code
- Test thoroughly
- Deploy fixed version
- Manually run patch if needed
