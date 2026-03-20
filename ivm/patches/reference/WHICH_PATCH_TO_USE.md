# Which Patch Should I Use?

Quick decision tree to help you choose the right patch approach for your scenario.

---

## Scenario 1: Changing Field Type

**Question**: Do you have existing production data in this field?

### ✅ NO - No production data yet

**Best approach**: Just update the DocType JSON directly.

```bash
# NO PATCH NEEDED!
# 1. Edit your DocType JSON or custom field definition
# 2. Change fieldtype from "Data" to "Attach" (or whatever)
# 3. Commit and deploy
# 4. Run bench migrate

cd frappe-bench
bench migrate
```

✨ **This is the simplest approach when you have no data to preserve.**

---

### ⚠️ YES - Have production data that must be preserved

**Best approach**: Use a patch to rename the field first.

#### Option A: Simple Rename (RECOMMENDED)

Use: [`migrate_project_wrap_layout_to_legacy.py`](migrate_project_wrap_layout_to_legacy.py)

**Process**:
1. Patch renames DB column: `wrap_layout` → `legacy_wrap_layout`
2. Update DocType JSON to reflect the rename
3. Add NEW `wrap_layout` field with Attach type
4. Deploy

**Code**:
```python
from frappe.model.utils.rename_field import rename_field

def execute():
    if frappe.db.has_column("Project", "wrap_layout"):
        rename_field("Project", "wrap_layout", "legacy_wrap_layout")
```

**When to use**: You want to keep old text data accessible AND have a new field with the same name but different type.

---

#### Option B: In-Place Type Change

**Approach**: Let Frappe change the column type directly.

**Process**:
1. Just change `fieldtype` in DocType JSON
2. No patch needed
3. Deploy and run migrate

**Risk**: Data may be lost or corrupted if types are incompatible (e.g., Data → Attach).

**When to use**: Field types are compatible (e.g., Data → Text, Int → Float)

---

## Scenario 2: Removing Select Field Options

**Example**: Your Select field has options ["A", "B", "C"], but you want to remove "B".

**Problem**: Existing records may use "B" and will fail validation after you remove it.

**Solution**: Use [`remap_select_field_options.py`](remap_select_field_options.py)

**Process**:
1. Create patch to remap "B" → "A" (or whatever)
2. Run the patch to update existing records
3. Update DocType JSON to remove "B" from options
4. Deploy

**Code**:
```python
def execute():
    remap_single_field(
        doctype="Project",
        fieldname="status",
        mapping={
            "On Hold": "Active",      # Remap "On Hold" to "Active"
            "Deprecated": "Current",   # Remap "Deprecated" to "Current"
        }
    )
```

**When to use**: Cleaning up old Select options while preserving data integrity.

---

## Scenario 3: Just Renaming a Field

**No type change, just want a better field name.**

**Best approach**: Use `rename_field()`

**Process**:
1. Create simple patch:
   ```python
   from frappe.model.utils.rename_field import rename_field
   
   def execute():
       rename_field("DocType", "old_name", "new_name")
   ```
2. Update DocType JSON to use new field name
3. Update any Python code that references the old name
4. Deploy

**When to use**: Simple field renaming with no type or data changes.

---

## Scenario 4: Complex Data Transformation

**Example**: Converting phone numbers from "1234567890" to "+1 (123) 456-7890"

**Best approach**: Use SQL or ORM with custom logic.

See: [`rename_wrap_layout_field_migration.py`](rename_wrap_layout_field_migration.py) for examples.

**Process**:
1. Create patch with transformation logic
2. Use batching for large datasets
3. Test thoroughly on copy of production data

**When to use**: Need to clean, format, or transform existing data.

---

## Quick Reference Table

| Scenario | Have Data? | Best Approach | Patch File |
|----------|-----------|---------------|------------|
| Change field type | ❌ No | Just update JSON, no patch | None needed |
| Change field type | ✅ Yes | Rename old field, add new | `migrate_project_wrap_layout_to_legacy.py` |
| Remove Select options | ✅ Yes | Remap to valid options | `remap_select_field_options.py` |
| Rename field (no type change) | Any | Use rename_field() | `TEMPLATE_patch.py` |
| Transform/clean data | ✅ Yes | Custom patch with logic | `rename_wrap_layout_field_migration.py` (examples) |

---

## Decision Tree Flowchart

```
Do you need to migrate data?
├─ NO → Just update DocType JSON, no patch needed
│
└─ YES → What type of change?
    │
    ├─ Field Type Change
    │  ├─ Want to keep old data separate? → migrate_project_wrap_layout_to_legacy.py
    │  └─ Want to convert in place? → Custom transformation patch
    │
    ├─ Remove Select Options
    │  └─ Records use removed options? → remap_select_field_options.py
    │
    ├─ Rename Field (no type change)
    │  └─ Use rename_field() in simple patch
    │
    └─ Transform/Clean Data
       └─ Custom patch with your logic
```

---

## Your Specific Questions Answered

### Q: "Must I have the new field already on the doctype during migration?"

**A**: It depends on your approach:

- **Using `rename_field()`**: NO, you don't need a new field first. It renames the actual database column and all metadata at once.

- **Using SQL to copy data**: YES, the target field must exist before copying data to it.

**Recommended**: Use `rename_field()` - it's simpler and safer.

---

### Q: "Is there a way to just make sure the incoming data is renamed?"

**A**: YES! That's exactly what `rename_field()` does:

```python
# This literally renames the database column
rename_field("Project", "old_field", "new_field")

# After this:
# - Database column is renamed
# - All existing data is preserved
# - Field no longer exists with old name
```

Then you can add a NEW field with the old name and different type.

---

### Q: "I want to remove some Select options but map them to different values"

**A**: YES, use [`remap_select_field_options.py`](remap_select_field_options.py):

```python
# Before: Options are ["Option A", "Option B", "Option C"]
# Goal: Remove "Option B", map it to "Option A"

def execute():
    remap_single_field(
        doctype="YourDocType",
        fieldname="your_select_field",
        mapping={
            "Option B": "Option A",  # Map old → new
        }
    )

# After running patch, update DocType JSON to only have ["Option A", "Option C"]
```

---

## Testing Checklist

Before using any patch:

1. ✅ **Backup database**
   ```bash
   bench --site your-site.local backup
   ```

2. ✅ **Test on database copy first**
   ```bash
   # Restore backup to test site
   bench --site test-site.local restore backup.sql.gz
   bench --site test-site.local migrate
   ```

3. ✅ **Verify data after migration**
   ```bash
   bench --site test-site.local console
   >>> frappe.db.sql("SELECT * FROM tabProject LIMIT 5", as_dict=True)
   ```

4. ✅ **Check for errors**
   ```bash
   tail -f sites/your-site.local/logs/bench.log
   ```

---

## Still Confused?

1. Start with [`TEMPLATE_patch.py`](TEMPLATE_patch.py) for structure
2. See [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md) for common operations
3. Read [`README_PATCHES.md`](README_PATCHES.md) for comprehensive guide
4. Look at [`add_hubspot_custom_fields.py`](add_hubspot_custom_fields.py) for a real working example

**Key principle**: Always prefer Frappe's built-in utilities (`rename_field`, etc.) over custom SQL when possible.
