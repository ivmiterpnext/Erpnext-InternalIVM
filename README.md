## IVM

IVM customizations

## Dev Environment: Syncing Prod Data

### One-Time Setup: Prerequisites

To enable automated production backup restoration:

- **Azure CLI authenticated**: Run `az login` with an identity that has read access to the `ivm-apps-dev-kv-01` Key Vault.
- **Frappe Cloud API credentials in Key Vault**: The secrets `FrappeCloud-ApiKey` and `FrappeCloud-ApiSecret` must already exist in the vault (seeded by whoever administers it).

The `restore_from_prod.sh` script fetches these credentials automatically from Key Vault — no local credential files needed.

### Regular Use: Restore Latest Prod Backup to Dev

To pull the latest production (ivmportal.frappe.cloud) backup and restore it to dev.local:

```bash
./scripts/restore_from_prod.sh
```

This script:
1. Fetches the latest successful backup from Frappe Cloud via API
2. Downloads it to `/tmp/ivm-prod-restore/`
3. Restores the database to dev.local
4. **Preserves dev's site_config.json** — your local DB credentials, encryption key, and integration API keys are not overwritten
5. Resets the admin password to `admin`
6. Runs migrations and clears caches
7. Prints sanity-check row counts (CRM Deals, Contacts, Items)

### Manual Fallback: Restore from Downloaded Backup

If you've manually downloaded a backup from the Frappe Cloud dashboard (**Settings → Backups → Download**), restore it directly:

```bash
./scripts/restore_from_prod.sh /path/to/downloaded-backup.sql.gz
```

This skips the API fetch and restores from the local file instead.

### HubSpot Webhook Testing in Dev

Both production and dev receive live HubSpot webhooks via a [Hookdeck](https://hookdeck.com) relay that fans out from a single HubSpot app webhook target to two destinations.

To receive webhooks on dev.local, use the [Hookdeck CLI](https://hookdeck.com/docs/cli) to forward events straight to your local server — no separate tunneling tool required:

```bash
hookdeck listen 8000 hubspot --path /api/method/ivm.integrations.hubspot.webhook.handle_webhook
```

(Replace `hubspot` with your actual Hookdeck source name if it differs.) This attaches your local session directly to the "dev" destination and forwards matching events to `localhost:8000` for the duration of the session — no public URL to generate or destination URL to update between dev sessions.

#### License

MIT
