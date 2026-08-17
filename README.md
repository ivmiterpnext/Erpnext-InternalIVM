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

Production receives live HubSpot webhooks directly (no relay service in between). Production then forwards a best-effort copy of each raw webhook payload to a dev tunnel URL, configured via the `hubspot_dev_relay_url` site config key on prod. If dev is offline, the forward silently fails — this is expected.

To receive webhooks on dev.local, use [ngrok](https://ngrok.com) to expose `localhost:8000` at a persistent, free static domain (one is included per ngrok account, and does not change between sessions):

**One-time setup:**
```bash
ngrok config add-authtoken <your-token>
```
Then claim your account's one free static domain via the [ngrok dashboard](https://dashboard.ngrok.com) (Domains page).

**Each dev session:**
```bash
ngrok http --url=https://<your-domain>.ngrok-free.app 8000
```

No changes are needed on prod between sessions since the domain is stable — `hubspot_dev_relay_url` is set once via `bench --site ivmportal.frappe.cloud set-config hubspot_dev_relay_url "https://<your-domain>.ngrok-free.app/api/method/ivm.integrations.hubspot.webhook.handle_webhook"`.

#### License

MIT
