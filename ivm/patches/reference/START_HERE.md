# Patch Guide: TL;DR

## If you DO have production data to preserve

### For Field Type Changes

**Use this patch**: [`migrate_project_wrap_layout_to_legacy.py`](migrate_project_wrap_layout_to_legacy.py)

**What it does**: Renames your old field so you can create a new one with the same name but different type.

**Steps**:
1. Edit the patch file, update these lines:
   ```python
   old_fieldname = "custom_wrap_layout"  # Your current field
   new_fieldname = "custom_legacy_wrap_layout"  # New name for old data
   ```

2. Add to [`patches.txt`](patches.txt):
   ```
   ivm.patches.migrate_project_wrap_layout_to_legacy
   ```

3. Run:
   ```bash
   bench migrate
   ```

4. After patch runs, update your DocType JSON to add NEW field with Attach type

---

### For Removing Select Options

**Use this patch**: [`remap_select_field_options.py`](remap_select_field_options.py)

**What it does**: Changes existing data from removed options to valid options.

**Steps**:
1. Edit the patch file, update the mapping:
   ```python
   remap_single_field(
       doctype="Project",
       fieldname="status",
       mapping={
           "Old Option Being Removed": "Valid Option To Use Instead",
           "Another Old Option": "Another Valid Option",
       }
   )
   ```

2. Add to [`patches.txt`](patches.txt):
   ```
   ivm.patches.remap_select_field_options
   ```

3. Run:
   ```bash
   bench migrate
   ```

4. After patch runs, update DocType JSON to remove old options

---

## File Guide

| File | Purpose |
|------|---------|
| `WHICH_PATCH_TO_USE.md` | ← **START HERE** - Decision guide |
| `QUICK_REFERENCE.md` | Code snippets & commands |
| `README_PATCHES.md` | Comprehensive documentation |
| `TEMPLATE_patch.py` | Blank template for new patches |
| `migrate_project_wrap_layout_to_legacy.py` | **USE THIS** for field type changes |
| `remap_select_field_options.py` | **USE THIS** for Select option cleanup |
| `rename_wrap_layout_field_migration.py` | Teaching examples (don't use directly) |

---

## Common Mistakes

❌ **Using a patch when you don't need one**
- If no production data exists, just update the JSON directly

❌ **Using `rename_wrap_layout_field_migration.py` directly**
- That's a teaching example, not a real patch

❌ **Not testing on a backup first**
- Always test patches on a database copy before production

❌ **Forgetting to update patches.txt**
- Patches won't run unless registered in `patches.txt`

---

## Your Two Scenarios

### Scenario 1: wrap_layout field type change

**Current**: Text/Data field  
**Want**: Attach field with same name  
**Have data?**: You said no new data yet

**Solution**: **NO PATCH NEEDED!** Just change the JSON.

```bash
# 1. Edit ivm/ivm/custom/project.json
# 2. Find custom_wrap_layout field definition
# 3. Change "fieldtype": "Data" to "fieldtype": "Attach"
# 4. Commit, deploy, migrate
```

### Scenario 2: Remove options from Select field

**Current**: Select field with options A, B, C  
**Want**: Remove option B, but records use it  
**Need**: Map B → A before removing

**Solution**: Use [`remap_select_field_options.py`](remap_select_field_options.py)

1. Copy and customize the patch
2. Register in `patches.txt`
3. Run `bench migrate`
4. Update DocType JSON to remove option B

---

## Quick Testing

```bash
# 1. Backup first
bench --site your-site.local backup

# 2. Run migration
bench --site your-site.local migrate

# 3. Check results
bench --site your-site.local console
>>> frappe.db.get_value("Project", "PROJ-001", ["name", "custom_wrap_layout"], as_dict=True)

# 4. If something goes wrong, restore
bench --site your-site.local restore /path/to/backup.sql.gz
```

---

## Need Help?

1. **Decision unclear?** → Read [`WHICH_PATCH_TO_USE.md`](WHICH_PATCH_TO_USE.md)
2. **Need code examples?** → See [`QUICK_REFERENCE.md`](QUICK_REFERENCE.md)
3. **Want full details?** → Read [`README_PATCHES.md`](README_PATCHES.md)
4. **Creating new patch?** → Copy [`TEMPLATE_patch.py`](TEMPLATE_patch.py)
