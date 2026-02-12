# IMPORTANT: Do Not Edit These Files Manually

These JSON files are **auto-managed** from the database when you make changes in the Customize Form UI.

## Workflow
1. Go to **Customize Form** in Frappe/ERPNext UI
2. Select the DocType you want to customize (e.g., Project, Contact, etc.)
3. Make your changes (add fields, modify properties, reorder, etc.)
4. Click **Update**
5. The corresponding JSON file in this directory will be **automatically updated**
6. You'll see a notification: "Auto-exported customizations for [DocType]"
7. Commit the updated JSON file to git

## DO NOT
- Manually edit these JSON files directly in your code editor
- Revert git commits without cleaning up the UI first

## Why This Approach?
- **One-way sync**: JSON files sync TO database during migration, but don't auto-delete fields
- **Auto-export**: UI changes automatically update JSON files (only in developer mode)
- **Portability**: These files ensure your customizations work on fresh installs and cloud deployments

## If You Accidentally Edit Manually
1. **Revert your manual changes** in git
2. Make the same changes **in the UI** via Customize Form
3. The auto-export will update the JSON correctly
4. Commit the auto-generated version

**DO NOT** just delete the field from the JSON file - it will not remove it from the database!

## File Structure

Each file corresponds to one DocType:

- `project.json` → All Project customizations
- `contact.json` → All Contact customizations
- `opportunity.json` → All Opportunity customizations
- etc.

Each file contains:
- `custom_fields`: All custom fields added to the DocType
- `property_setters`: Field property modifications (hidden, required, depends_on, etc.)
- `custom_perms`: Custom permission rules (if any)
- `links`: DocType Link customizations (if any)
- `sync_on_migrate`: Set to 1 to auto-sync during migrations

## Developer Mode Only

Auto-export only works when:
- `developer_mode = 1` in `site_config.json`
- You're making changes via the UI (not via code/migrations)

On production sites (developer mode off), these files don't auto-update.
