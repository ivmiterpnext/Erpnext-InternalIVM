# Inventory Reconciliation Runbook — ivmportal.frappe.cloud

## Prerequisites (already confirmed)
- Bench container: `bench-33751-000050-hybridf0h`
- Bench root inside container: `/home/frappe/frappe-bench`
- Site: `ivmportal.frappe.cloud`
- openpyxl 3.1.5 available in bench python env
- Both source files uploaded via Frappe Desk (Files) and confirmed present at:
  - `/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/Inventory 6.2026.xlsx`
  - `/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/Parts list with Prices 7.2026.xlsx`

## Step 1: Upload the script

Upload `inventory_recon.py` via the Frappe Desk (Files list, Private) the same way the two xlsx files were uploaded. Confirm it landed on disk:

```bash
sudo docker exec bench-33751-000050-hybridf0h bash -c "ls -la '/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/' | grep inventory_recon"
```

## Step 2: Get an interactive shell inside the container

Do not try to chain everything into one `docker exec` one-liner from the host — the quoting nests too deeply (docker exec args -> bash -c -> bench execute args) and is fragile. Instead:

```bash
sudo docker exec -it bench-33751-000050-hybridf0h bash
```

Your prompt should change to something like `frappe@<container-id>:~/frappe-bench$`. All remaining commands in this runbook are run from inside that shell.

## Note on the execute command

`bench execute` internally runs `eval(code, globals(), locals())` with two separate dict objects. If the inner `exec(open(path).read())` is called with no explicit namespace, Python treats the script's top-level code as running in class-body-like scope: every `def` gets stored in `locals()`, but each function object's `__globals__` still points at the separate outer `globals()` dict. This means sibling functions (`log`, `resolve_company`, etc.) cannot see each other, causing `NameError` inside `main()`. Passing `globals()` explicitly as the second argument to the inner `exec()` collapses globals and locals back into a single namespace, restoring normal module-level function resolution. This is why the commands below include `, globals())` at the end of the `exec()` call — do not omit it.

## Step 3: Dry run

```bash
bench --site ivmportal.frappe.cloud execute "exec(open('/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/inventory_recon.py').read(), globals())"
```

Review the full output carefully:
- Company auto-detected correctly?
- Any missing items or warehouses listed as warnings?
- Any negative-quantity-clamped warnings — how many, and do they look reasonable given known small transaction volume since 2026-07-10?
- Total reconciliation value and row count — sanity check against expectations.
- Confirms `DRY RUN -- no documents were created.`

Do not proceed to Step 4 until this output has been reviewed and looks correct.

## Step 4: Live run

Edit the script to flip the flag:

```bash
sed -i 's/^DRY_RUN = True/DRY_RUN = False/' "/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/inventory_recon.py"
```

Re-run the same command:

```bash
bench --site ivmportal.frappe.cloud execute "exec(open('/home/frappe/frappe-bench/sites/ivmportal.frappe.cloud/private/files/inventory_recon.py').read(), globals())"
```

Confirm the summary shows `Stock Reconciliation docs submitted:` with a list of document names, and `Changes committed.` at the end.

## Step 5: Verify

From the Frappe Desk UI:
1. Open Stock Balance report, spot-check 10-15 items/bays against the original spreadsheet values.
2. Open a couple of the created Stock Reconciliation documents, confirm status is Submitted (not Draft).
3. Check Item Price list under Standard Buying for a sample of items.
4. Check Build In Progress warehouse stock is unaffected.

## Step 6: Clean up

Delete the uploaded xlsx files and the script from the Files list in the Desk UI once verification is complete, since they contain internal cost/inventory data and no longer need to sit on the server.

## Backup reminder

A site backup should be taken before Step 4 (live run). From the Frappe Cloud dashboard: Site > Backups > Create Backup. This is independent of the SSH session and should be done via the dashboard, not manually via bench inside this container.
