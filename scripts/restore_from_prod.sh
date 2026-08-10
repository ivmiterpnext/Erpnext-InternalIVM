#!/bin/bash
set -euo pipefail

# Restore dev.local database from latest production (ivmportal.frappe.cloud) backup
#
# Usage:
#   ./scripts/restore_from_prod.sh                    # Automated: fetch latest backup via Frappe Cloud API
#   ./scripts/restore_from_prod.sh /path/to/backup.sql.gz  # Manual: restore from local backup file

# Configuration
SITE="dev.local"
PROD_SITE="ivmportal.frappe.cloud"
FC_URL="https://cloud.frappe.io"
BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKUP_DIR="/tmp/ivm-prod-restore"
SITE_CONFIG="$BENCH_DIR/sites/$SITE/site_config.json"
DB_ROOT_USER="root"
DB_ROOT_PASSWORD="root_dev_local"

# Determine mode: manual (file path given) or automated (fetch from API)
BACKUP_FILE=""
MANUAL_MODE=false

if [ $# -gt 0 ]; then
    MANUAL_MODE=true
    BACKUP_FILE="$1"
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "Error: Backup file not found: $BACKUP_FILE"
        exit 1
    fi
    echo "Manual mode: using backup file $BACKUP_FILE"
else
    echo "Automated mode: fetching latest backup from Frappe Cloud API"
fi

# ============================================================================
# AUTOMATED MODE: Fetch backup from Frappe Cloud API
# ============================================================================

if [ "$MANUAL_MODE" = false ]; then
    # Check jq is installed
    if ! command -v jq &> /dev/null; then
        echo "Error: jq is required for JSON parsing but not installed."
        echo "Install it with: sudo apt-get install jq (Debian/Ubuntu) or brew install jq (macOS)"
        exit 1
    fi
    
    echo "Fetching Frappe Cloud credentials from Azure Key Vault..."
    FC_CREDS_JSON=$(cd "$BENCH_DIR" && bench --site "$SITE" execute \
      "ivm.integrations.keyvault.get_secrets" \
      --kwargs "{'names': ['FrappeCloud-ApiKey', 'FrappeCloud-ApiSecret']}" 2>&1)

    if [ -z "$FC_CREDS_JSON" ] || ! echo "$FC_CREDS_JSON" | jq -e . >/dev/null 2>&1; then
        echo "Failed to fetch Frappe Cloud credentials from Key Vault." >&2
        echo "Output was: $FC_CREDS_JSON" >&2
        echo "" >&2
        echo "Verify:" >&2
        echo "  - Secrets 'FrappeCloud-ApiKey' and 'FrappeCloud-ApiSecret' exist in the ivm-apps-dev-kv-01 vault" >&2
        echo "  - Your Azure identity has read access (check with: az account show)" >&2
        echo "  - azure_keyvault_url is set correctly in sites/dev.local/site_config.json" >&2
        echo "" >&2
        echo "Alternatively, pass a backup file directly:" >&2
        echo "  ./scripts/restore_from_prod.sh /path/to/backup.sql.gz" >&2
        exit 1
    fi

    FC_API_KEY=$(echo "$FC_CREDS_JSON" | jq -r '."FrappeCloud-ApiKey"')
    FC_API_SECRET=$(echo "$FC_CREDS_JSON" | jq -r '."FrappeCloud-ApiSecret"')

    if [ -z "$FC_API_KEY" ] || [ "$FC_API_KEY" = "null" ] || [ -z "$FC_API_SECRET" ] || [ "$FC_API_SECRET" = "null" ]; then
        echo "Key Vault returned empty values for FrappeCloud-ApiKey or FrappeCloud-ApiSecret." >&2
        echo "Verify the secrets are seeded correctly in the ivm-apps-dev-kv-01 vault." >&2
        exit 1
    fi

    echo "Credentials retrieved successfully."
    echo ""
    echo "Fetching backup list from Frappe Cloud..."
    
    # Fetch backup list
    BACKUP_LIST_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: token $FC_API_KEY:$FC_API_SECRET" \
        "$FC_URL/api/method/press.api.site.backups?name=$PROD_SITE")
    
    HTTP_CODE=$(echo "$BACKUP_LIST_RESPONSE" | tail -n1)
    BACKUP_LIST_BODY=$(echo "$BACKUP_LIST_RESPONSE" | head -n-1)
    
    if [ "$HTTP_CODE" != "200" ]; then
        echo "Error: Failed to fetch backup list (HTTP $HTTP_CODE)"
        echo "Response: $BACKUP_LIST_BODY"
        exit 1
    fi
    
    # Parse backup list: filter for successful backups, sort by creation descending, take first
    BACKUP_INFO=$(echo "$BACKUP_LIST_BODY" | jq -r '.message | map(select(.status == "Success")) | sort_by(.creation) | reverse | .[0] | "\(.name)|\(.creation)"' 2>/dev/null)
    
    if [ -z "$BACKUP_INFO" ] || [ "$BACKUP_INFO" = "null" ]; then
        echo "Error: No successful backups found for $PROD_SITE"
        exit 1
    fi
    
    BACKUP_ID=$(echo "$BACKUP_INFO" | cut -d'|' -f1)
    BACKUP_DATE=$(echo "$BACKUP_INFO" | cut -d'|' -f2)
    
    echo "Latest successful backup: $BACKUP_ID (created: $BACKUP_DATE)"
    echo ""
    echo "Fetching download link..."
    
    # Fetch download link
    DOWNLOAD_LINK_RESPONSE=$(curl -s -w "\n%{http_code}" \
        -H "Authorization: token $FC_API_KEY:$FC_API_SECRET" \
        "$FC_URL/api/method/press.api.site.get_backup_link?name=$PROD_SITE&backup=$BACKUP_ID&file=database")
    
    HTTP_CODE=$(echo "$DOWNLOAD_LINK_RESPONSE" | tail -n1)
    DOWNLOAD_LINK_BODY=$(echo "$DOWNLOAD_LINK_RESPONSE" | head -n-1)
    
    if [ "$HTTP_CODE" != "200" ]; then
        echo "Error: Failed to fetch download link (HTTP $HTTP_CODE)"
        echo "Response: $DOWNLOAD_LINK_BODY"
        exit 1
    fi
    
    DOWNLOAD_URL=$(echo "$DOWNLOAD_LINK_BODY" | jq -r '.message' 2>/dev/null)
    
    if [ -z "$DOWNLOAD_URL" ] || [ "$DOWNLOAD_URL" = "null" ]; then
        echo "Error: Could not extract download URL from response"
        exit 1
    fi
    
    # Create backup directory and download
    mkdir -p "$BACKUP_DIR"
    
    echo "Downloading backup..."
    curl -L -o "$BACKUP_DIR/prod-latest.sql.gz" "$DOWNLOAD_URL"
    
    # Verify downloaded file
    if [ ! -f "$BACKUP_DIR/prod-latest.sql.gz" ] || [ ! -s "$BACKUP_DIR/prod-latest.sql.gz" ]; then
        echo "Error: Downloaded backup file is empty or missing"
        exit 1
    fi
    
    # Check file is gzip
    if ! file "$BACKUP_DIR/prod-latest.sql.gz" | grep -q gzip; then
        echo "Error: Downloaded file does not appear to be gzip format"
        file "$BACKUP_DIR/prod-latest.sql.gz"
        exit 1
    fi
    
    BACKUP_FILE="$BACKUP_DIR/prod-latest.sql.gz"
    echo "✓ Backup downloaded successfully"
fi

# ============================================================================
# RESTORE PROCESS (both modes)
# ============================================================================

echo ""
echo "=== Starting Restore Process ==="
echo ""

# Ensure backup directory exists for site_config backup
mkdir -p "$BACKUP_DIR"

# Snapshot dev's current site_config.json
echo "Backing up current site_config.json..."
cp "$SITE_CONFIG" "$BACKUP_DIR/site_config.json.bak"

# Run restore
echo "Restoring database from: $BACKUP_FILE"
cd "$BENCH_DIR"
if ! bench --site "$SITE" restore --db-root-username "$DB_ROOT_USER" --db-root-password "$DB_ROOT_PASSWORD" "$BACKUP_FILE"; then
    echo "Error: bench restore failed"
    exit 1
fi

# Restore dev's site_config.json (preserves DB credentials, encryption key, API keys)
echo "Restoring site_config.json (preserving dev credentials)..."
cp "$BACKUP_DIR/site_config.json.bak" "$SITE_CONFIG"

# Reset admin password
echo "Resetting admin password..."
if ! bench --site "$SITE" set-admin-password admin; then
    echo "Error: Failed to set admin password"
    exit 1
fi

# Run migrations
echo "Running migrations..."
if ! bench --site "$SITE" migrate; then
    echo "Error: Migration failed"
    exit 1
fi

# ============================================================================
# SAFETY: Disable live email sync/send on dev — prod's DB dump re-enables
# these flags on every restore; re-disable them here so dev never polls or
# sends through real company mailboxes. mute_emails itself already survives
# restores via the site_config.json preserve step above, but pinned here too
# for redundancy.
# ============================================================================

echo ""
echo "Re-applying dev email safety settings..."

bench --site "$SITE" set-config mute_emails 1

if ! bench --site "$SITE" execute "frappe.db.set_value('Email Account', ['Accounts Receivables', 'ICS Support', 'IT Support', 'IVM Support', 'Vending Management'], {'enable_incoming': 0})"; then
    echo "Warning: Failed to disable incoming mail sync on dev (non-fatal)"
fi

if ! bench --site "$SITE" execute "frappe.db.set_value('Email Account', ['Accounts Receivables', 'ICS Support', 'IVM Support', 'Vending Management'], {'enable_outgoing': 0})"; then
    echo "Warning: Failed to disable outgoing mail on dev O365 accounts (non-fatal)"
fi

# Rebuild frontend assets — migrate does not do this, and stale asset
# manifests (e.g. for the CRM Vue SPA) cause blank screens after a restore.
echo "Rebuilding frontend assets..."
if ! bench build; then
    echo "Error: Asset build failed"
    exit 1
fi

# Clear caches
echo "Clearing caches..."
if ! bench --site "$SITE" clear-cache; then
    echo "Error: Failed to clear cache"
    exit 1
fi

if ! bench --site "$SITE" clear-website-cache; then
    echo "Error: Failed to clear website cache"
    exit 1
fi

# Clean up the downloaded backup file — restore succeeded, no need to keep a
# ~5GB+ compressed dump around. Only removes auto-downloaded files, never a
# manually-supplied backup path.
if [ "$MANUAL_MODE" = false ]; then
    echo "Cleaning up downloaded backup file..."
    rm -f "$BACKUP_DIR/prod-latest.sql.gz"
fi

# ============================================================================
# SANITY CHECK: Print row counts
# ============================================================================

echo ""
echo "=== Sanity Check: Row Counts ==="

DEAL_COUNT=$(bench --site "$SITE" execute "frappe.db.count('CRM Deal')" 2>/dev/null || echo "?")
CONTACT_COUNT=$(bench --site "$SITE" execute "frappe.db.count('Contact')" 2>/dev/null || echo "?")
ITEM_COUNT=$(bench --site "$SITE" execute "frappe.db.count('Item')" 2>/dev/null || echo "?")

echo "CRM Deal records: $DEAL_COUNT"
echo "Contact records: $CONTACT_COUNT"
echo "Item records: $ITEM_COUNT"

# ============================================================================
# COMPLETION SUMMARY
# ============================================================================

echo ""
echo "=== Restore Complete ==="
echo "Timestamp: $(date)"

if [ "$MANUAL_MODE" = false ]; then
    echo "Backup ID: $BACKUP_ID"
    echo "Backup Date: $BACKUP_DATE"
else
    echo "Backup File: $BACKUP_FILE"
fi

echo ""
echo "Dev site ($SITE) has been restored from production ($PROD_SITE)."
echo "Site config (DB credentials, encryption key, API keys) has been preserved."
echo ""
