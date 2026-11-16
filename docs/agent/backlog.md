# Backlog

Known gaps and open questions surfaced during other work (test coverage audits, gotcha investigation, etc.) that weren't in scope to fix at the time. Each entry is written so a fresh agent can pick it up without re-deriving the discovery from scratch — read the listed files first, then the "Open questions" before proposing a fix.

## iCorp location + machine provisioning via Generate Build Requests (next increment after client attachment)

**Context (2026-11-05):** Deployment Projects now carry a real `icorp_client_id` (Link → iCorp Client Link, replacing the old free-text `client_id`, which stays on the doctype — relabelled "Legacy Client ID", read-only, hidden) plus a derived `partner_customer`. Each machine detail row (SmartStation/SmartLocker/SmartSync/SmartVault/SmartCenter) also has an optional per-row `icorp_client_id` override. The next increment is teaching the "Generate Build Requests" buttons to actually create the missing machine (and its location) in iCorp, instead of only reporting it's missing.

**Integration point:** `ivm/warehouse/services/warehouse_request.py::create_build_requests_from_detail_rows`. Today it only reads from iCorp — `fetch_machine()` is a GET, and if a row's machine isn't found there, the function returns it in a `failed` list and creates nothing (surfaced in `Project.js`'s `_generate_build_requests` as "The following machines were not found in iCorp..."). This is where "create the machine (and location) if missing" belongs.

**iCorp API facts** (confirmed 2026-11 via `<base>/swagger/v1/swagger.json`, fetched read-only using `ivm.integrations.icorp.api.get_icorp_auth()` headers):
- `POST SV/Machine` has **no client field**. Required: `name`, `locationId`, `machineTypeId`, `machineStatusTypeCode`, `machinePurposeId`, `machineAuthorizationId`, `allowSkipJobCode`, `usingJobCode`, `useMachineTimezone`. A machine belongs to a *location*, not directly to a client.
- `POST SV/Location` requires: `clientId`, `name`, `win32TimeZoneIndex`, `allowedVendsPerAuth`, `isAllowAnyoneVend`.

**Evidence that one site needs one iCorp location per iCorp client:** live Vodafone data — "Vodafone - Utrecht" is location 2916 under client 1629 ("Vodafone - Enhanced Lockers") and a *separate* location 2926 under client 1636 ("Vodafone - SmartStations"). Same site name, different location IDs, because the locker machines and the station machines were put under two different iCorp clients for that one customer. This is why Project's per-row `icorp_client_id` override exists — a single deployment site can span more than one iCorp client.

**Data gaps — nothing on Project or its detail child tables supplies these today:**
| iCorp field | Status |
|---|---|
| `machinePurposeId` | Not captured. The detail row's `workflow` Select *might* map to it (values seen in live data: "Regular vending machine", "Auto Vend Machine") — unconfirmed. |
| `machineAuthorizationId` | Not captured. Live sampled data was always "Badge authentication" — possibly a fixed default, unconfirmed. |
| `win32TimeZoneIndex` (on the Location, not the machine) | Not captured anywhere. |
| `allowedVendsPerAuth`, `isAllowAnyoneVend` (Location) | Not captured; likely safe to default. |

**Known breakage to fix as part of this work:**
- `ivm/deployments/services/create_machines_from_project.py` is non-functional: it references `project.location_id`, which doesn't exist on Project (its own comment flags this as a TODO), and it sets `Machine.client_id` (a Link → **Customer**, see `ivm/machine_hardware_management/doctype/machine/machine.json`) to an iCorp client ID string — a type mismatch / bug, not a design choice.

**Planned direction (not yet built):** a "Deployment iCorp Location" child table on Project, columns `{icorp_client_id, icorp_location_id, location_name}`, populated by the provisioning flow — one row per distinct client actually used across that Project's detail rows, supporting split-client sites like Vodafone/Pfizer.

**Where to find the swagger spec again:** `GET <ICORP_API_BASE_URL>/swagger/v1/swagger.json`, authenticated with the headers from `ivm.integrations.icorp.api.get_icorp_auth()` (same Azure AD ROPC flow as every other iCorp call in this app).

---

## Two Warehouse Request "subject" Server Scripts silently overwrite explicitly-set values

**Where to look first:**
- `ivm/fixtures/server_script.json` — two records, both `doctype_event: "Before Insert"`, `reference_doctype: "Warehouse Request"`:
  - `"Build Request Subject Generation"`: `if "Build" in doc.request_reason: doc.subject = 'Build Request: '+ doc.related_project`
  - `"Wrap Ready Subject"`: matches `"Wrap Ready" in doc.request_reason` **or** `"Build" in doc.request_reason`, and sets `doc.subject = str(doc.request_reason)+': ' + str(doc.project_name) + ' ' + str(doc.related_project)`
- `ivm/warehouse/services/warehouse_request.py` — `create_build_requests_from_detail_rows()` (~line 146) and `create_shipping_request_from_build()` (~line 316) both explicitly set `wr.subject = ...` before insert, apparently unaware their value gets overwritten.
- `ivm/warehouse/services/tests/test_warehouse_request.py::TestWarehouseRequestQuery` — the tests that surfaced this (had to switch `request_reason` to `"Shipping Request"` to get subject assertions to pass at all).

**What's confirmed (empirically, via test reproduction on 2026-09-16):**
Both scripts match any `request_reason` containing the substring `"Build"` (e.g. `"Build Machine"`, `"Build Locker"`, `"Build Kiosk"`, `"Build Vault"`). Whichever runs last wins — empirically, `"Wrap Ready Subject"`'s template won for a `"Build Machine"` reason (observed subject: `"Build Machine: None None"`, matching that script's template, not `"Build Request Subject Generation"`'s). Any caller — service-layer code or a human editing the form — that sets an explicit `subject` on a Build-type Warehouse Request has that value silently discarded and replaced with a system-generated one. No error, no warning.

**Open questions for whoever picks this up:**
1. Is this overwrite intentional, or a leftover from an older manual-creation UI flow that predates `schema_version 2`'s programmatic creation path? `create_build_requests_from_detail_rows()` sets its own subject template and its docstring gives no indication it expects to be overwritten.
2. Two scripts currently have overlapping trigger conditions (both fire for any `"Build"` reason). Is that intentional (a deliberate "last one wins" fallback chain), or should one be removed/scoped down?
3. Server Script execution order across two independently-created records on the same doctype event isn't something to assume is stable across environments — confirm what actually determines the order (idx? creation timestamp?) before relying on "Wrap Ready Subject always wins" as a fact rather than an observation from one test run.
4. Should this be scoped to `schema_version == 1` (legacy manual-entry flow) so `schema_version 2`'s explicit subject-setting isn't fought?

---

## Should 4 of Project's due-date fields ever vary by locale (Domestic/International)?

**Where to look first:**
- `ivm/deployments/event_handlers/project.py` — `_DUE_DATE_RULES` table. 5 rows (`provide_planogram_due`, `approve_planogram_and_locker_config_due`, `pog_created_in_database_due`, `sample_products_due`, `sample_badge_due`) have genuinely different `domestic_days`/`international_days` values. The other 4 rows (`delivery_and_install_contact_due_customs`, `delivery_install_and_coi_requirements`, `user_and_restriction_requirements_due`, `graphic_design_approval_due`) have identical `domestic_days`/`international_days` values in every row — i.e. locale has never actually affected these 4 fields, only `expedited_delivery` does.

**What's confirmed:**
`delivery_and_install_contact_due_customs`'s own field label is "Delivery & Install Contact Due (Customs)", and it sits next to `customs_contact`/`customs_contact_phone`/`customs_contact_email` fields — "customs" normally implies an international/cross-border-shipping-specific concern, which would suggest this field's due date should logically vary by locale. However, production data on `dev.local` contradicts a clean international-only reading: `customs_contact` is populated on both Domestic (122 projects) and International (255 projects) records, and `delivery_and_install_contact_due_customs` is computed at essentially identical rates for both locales (73.5% of Domestic projects, 73.4% of International). So "customs" doesn't map cleanly onto this app's `locale` field in current usage — it's not evidence the current locale-blindness is wrong, but the naming is suggestive enough that it shouldn't be assumed correct either.

No similar signal exists for the other 3 fields (COI requirements, user/restriction requirements, graphic design/wrap approval) — no obvious reason a certificate-of-insurance deadline or a wrap-design-approval timeline would inherently depend on domestic vs. international placement.

**Open questions for whoever picks this up:**
1. Should any of these 4 fields' `domestic_days`/`international_days` values actually differ? This requires input from whoever owns deployment logistics/timelines, not something derivable from the code or current data.
2. If the answer is yes for `delivery_and_install_contact_due_customs` specifically (the customs-labeled one), what should the corrected values be, and should `customs_contact`'s own presence/requirement also be gated by locale (it currently isn't)?
3. This does not block anything currently shipped — the table structure already supports different domestic/international values per row with a one-line change once the correct values are known; no code restructuring required.

---

## Assignment Rules outside Warehouse Request are unaudited and untracked in version control

**Context:** `Warehouse Request Assignment` was found broken (assign_condition referenced a Custom Field deleted by
`ivm.warehouse.patches.drop_wr_dead_custom_fields` on 2026-08-12) and has now been fixed and added to fixtures
(`ivm/fixtures/assignment_rule.json`, scoped via filter to that one record). Eight other DB-only Assignment Rules
exist and were **not** included in that fix:

- Issue: `Azure Alerts`, `Azure Alerts 2`, `Defender Alert Assignments`, `IT Support`, `Case Owner`
- Task: `Equipment Notification Assignment`
- HD Ticket: `Billing`, `Product Experts`, `Support Rotation`

**Why not folded in automatically:** `sync_fixtures()` upserts on every `bench migrate` — whatever is exported from
dev becomes the enforced state on every site including prod. Unlike `Warehouse Request Assignment` (single user,
verified condition), these rules likely have per-environment differences (real on-call rosters in prod vs.
test/dummy users in dev) that a blind export would silently overwrite on next migrate.

**Before adding any of these to fixtures, for each rule:**
1. Confirm `rule` type (Round Robin / Load Balancing / Based on Field / Weighted Distribution) — Round Robin and
   Weighted Distribution actively depend on `last_user`/`current_index` as live rotation state; freezing those into
   a fixture and re-syncing on every migrate would break fair rotation (unlike Load Balancing, which ignores both).
2. Validate `assign_condition`/`unassign_condition`/`close_condition` actually evaluate without error against the
   doctype's current schema (same class of bug found in Warehouse Request Assignment could be silently present in
   any of these already).
3. Confirm with the owning team (IT/Support/Billing, not necessarily warehouse ops) whether dev and prod are
   *intended* to share identical rosters, or whether prod-only config is deliberate.
4. Only then decide per-rule whether to add to `ivm/hooks.py`'s `fixtures` list.

**Open question:** should this be one audit pass covering all 8, or handled per-team as each rule surfaces its own
issue?

---

## `bench export-fixtures --app ivm` re-exports every fixture doctype in `hooks.py`, not just the one you changed — 10 unrelated files blew up when adding a single Custom DocPerm

**Context (2026-09-23):** Adding one `Custom DocPerm` record (`Stock Manager` read-only on `Sales Taxes and Charges
Template`, mirroring a same-day prod fix) required running `bench --site dev.local export-fixtures --app ivm` to
pick it up into `ivm/fixtures/custom_docperm.json`. That command has no per-doctype scoping — `--app` is the only
flag (`bench export-fixtures --help`), and it re-serializes **every** doctype `ivm/hooks.py`'s `fixtures` list
declares, regardless of what you actually changed. The same run that added our one Custom DocPerm record also
modified 10 other fixture files:

```
ivm/fixtures/client_script.json        |    44 +
ivm/fixtures/custom_field.json         | 13615 ++++++++++++++++++++---------
ivm/fixtures/list_view_settings.json   |    19 +-
ivm/fixtures/property_setter.json      |   500 +-
ivm/fixtures/report.json               |   290 +
ivm/fixtures/role.json                 |    13 +
ivm/fixtures/server_script.json        |    19 +
ivm/fixtures/workspace.json            |  3177 +++-
ivm/fixtures/workspace_shortcut.json   |  1302 ++++
ivm/fixtures/workspace_sidebar.json    |   401 +-
```

None of these were reviewed line-by-line before being reverted (`git checkout --`) — the diffs were too large to
audit in the moment (13,615 lines alone for `custom_field.json`). They were discarded unexamined rather than risk
committing unreviewed drift, but that means **the underlying question — how much of that is real, previously-
unexported dev.local DB state vs. how much is stale/wrong/reformatting noise — is still completely open.**

**What's confirmed, from the one file that *was* reviewed (`custom_docperm.json`, 258 insertions / 76 deletions for
what should have been a single new record):** the diff was a mix of two unrelated things:
1. Genuine new DB records that existed in `dev.local` but had never been exported before (e.g. `Warehouse` role
   gaining read access to `Warehouse` and `Pick List` doctypes) — real drift, just previously stale in the fixture.
2. Pure whitespace/indentation re-serialization of ~75 *other* unrelated existing entries with no data change at all
   (e.g. record `h67ge861bc` on `CRM Task` — identical fields, just re-indented).

There's no reason to expect the other 10 files are any different in kind — likely the same blend of real drift +
cosmetic noise, just at a much larger scale (`custom_field.json` and `workspace.json` in particular are large,
frequently-hand-edited fixture files where "real drift" could mean anything from a legitimate field added by another
session to an accidental duplicate).

**Open questions for whoever picks this up:**
1. Diff each of the 10 files individually against current `dev.local` DB state and current fixture JSON to separate
   real drift from reformatting noise — probably needs a script that normalizes JSON indentation before diffing, to
   strip out the cosmetic noise class entirely and surface only semantic changes.
2. For any genuine drift found: was it intentional (someone customized something in Desk deliberately) or
   accidental/experimental (a test change on the shared dev site that was never meant to be permanent)? This
   determines whether it should be committed to fixtures at all.
3. Should high-churn, frequently-diverging fixtures like `custom_field.json` and `property_setter.json` get a
   narrower export path — e.g. a small wrapper script that calls the underlying per-doctype export function directly
   (bypassing the all-or-nothing `--app` CLI) — so a single-record addition doesn't force a full-file re-diff every
   time? Check whether `frappe.model.utils.rename_doc`-adjacent tooling or `frappe.core.doctype....export_fixtures`
   internals expose a per-doctype entry point before assuming this needs custom tooling from scratch.
4. This is the same underlying failure mode as the `Custom Field`/`lms` cross-app corruption gotcha already
   documented in this app's `CLAUDE.md` (bare, unscoped fixture doctype names in `hooks.py` export "everything,
   site-wide" rather than "just what this app cares about") — except here it bit `ivm`'s own fixtures, not another
   app's. Worth asking whether any of these 10 doctypes should get a scoping filter dict in `hooks.py` (the way
   `Desktop Icon`, `Workspace Sidebar`, `Print Format`, `Report`, and `Assignment Rule` already do) to shrink the
    blast radius of future single-record additions.

---

## HubSpot bundled-app cutover prep complete (code changes only, not yet uploaded)

**Status as of 2026-10-02:** All code changes for the new bundled app (`ivm_hubspot_integration`) and legacy app switch-off are complete and committed locally. Nothing has been uploaded to HubSpot yet.

**What's done:**
- New app project lives at `/home/lhammond/ivm_hubspot_integration` (git repo, name `ivm_hubspot_integration`). Contains:
  - `src/app/app-hsmeta.json` — finalized with 10 required scopes (legacy minus `crm.schemas.custom.write`), `https://portal.ivminc.com` as permittedUrl, no placeholder support block.
  - `src/app/webhooks/webhooks-hsmeta.json` — regenerated from field-map constants via `tools/generate_webhook_subscriptions.py`, all subscriptions inactive (ready for switch).
  - `staged/cards/` — app card moved out of `src/app/cards/` and excluded from first upload until quote-generation and quote-status Frappe endpoints exist (separate later release).
- Legacy app repull lives at `/home/lhammond/ivm_legacy_export` (git repo, downloaded state of app 31487585). Contains:
  - `main` branch — original live app state (184 active subscriptions).
  - `cutover/disable-subscriptions` branch — all 184 subscriptions flipped to inactive (ready to upload as switch-off copy).
- Webhook subscription generator created in `ivm/tools/generate_webhook_subscriptions.py` (with unit tests in `tools/tests/test_generate_webhook_subscriptions.py`). Generates deterministic JSON from field-map constants; validates every `SYNC_TARGETS` key has a corresponding object type.
- Property-list constants extracted in `ivm/integrations/hubspot/constants.py`: `COMPANY_PROPERTIES` and `CONTACT_PROPERTIES` (used by handlers and generator).

**What's not done (blocking next steps):**
- Field-map property names have not been validated against what properties actually exist in the HubSpot portal — this can only be confirmed once the new project is uploaded (first real upload will surface any build errors for nonexistent properties).
- v3 webhook signature verification (future hardening, not a precondition for cutover). When built, the signed URI must be constructed from a configured base URL (`https://portal.ivminc.com`), not from `frappe.request.url`, because Frappe Cloud's proxy can present `http://` or an internal host.

**Cutover sequence (when ready):**
1. Upload + deploy + install the new app with all subscriptions inactive; verify scopes from a dev site.
2. Separately finish and deploy Frappe-side prep work (outstanding fixes + a reconciliation job that polls by `hs_lastmodifieddate` and routes through `routing.route()`).
3. Actual switch: credential rotation in site_config (`hubspot_api_key`, `hubspot_client_secret`) + bench restart.
4. Upload legacy project's `cutover/disable-subscriptions` branch (subscriptions off).
5. Regenerate new project's webhooks with `--active=true` and upload (subscriptions on).

No parallel-run period — v1 signature verification (SHA-256 client-secret+body) works as soon as `hubspot_client_secret` holds the new app's secret, so the switch is atomic.

---

## Orphaned Contact Dynamic Link rows (parent Contact missing)

**Context (2026-11-11):** 3,277 `Dynamic Link` rows on dev.local have `parenttype = Contact` but no existing parent Contact. Example: Customer "Airbus" → parent "Airbus (TV)-Airbus (TV)". Likely left behind by customer consolidation merges/disables and the 2023 import.

- Code reading Contact links must tolerate these. `get_customer_contacts` now does (fixed 2026-11-11, see `icorp_client_link.py`).
- Candidate cleanup: patch that deletes Dynamic Link rows whose parent Contact is missing. Check prod's count before acting.

---

## Dev-only leftover: Customer "Ferguson," with iCorp client 900007

**Context (2026-11-11):** Customer "Ferguson," (trailing comma, likely duplicate of "Ferguson") is linked to dev iCorp client 900007 (`assignment_source` "Provisioning", created 2026-11-10) from the removed automatic iCorp provisioning.

- Dev cleanup candidate: merge/delete the Customer and deactivate 900007 in dev iCorp.
- Confirm prod has no equivalent before deploying.

---

## Dev iCorp client ID range (900000+)

**Context (2026-11-11):** Dev iCorp assigns new client IDs in the 900000+ range (900001–900008 so far). Prod uses its own sequence. Confirm with iCorp owners before relying on either range.

---

## Teardown deploy: drop legacy Customer / CRM Deal / Project master-client and import fields

**Context (2026-11):** Legacy fields are still on the doctypes. Remove them in one deploy, with their readers changed in the same commit.

- **Drop `Customer.icorp_client_id`.** Remove the field from `ivm/ivm/custom/customer.json`, drop the DB column, and update its readers together: `apply_customer_record_ids`, `set_customer_icorp_client_ids`, and `dry_run.gather_existing_customer_icorp_ids` (`ivm/customer_consolidation/`).
- **Finish `drop_customer_import_stat_fields`** (`ivm/customer_consolidation/patches/drop_customer_import_stat_fields.py`): remove its 14 fields from `customer.json` and `field_order`, delete the Accounts Audit report, clean up `ivm/public/js/doctype/Customer.js`, then register the patch.
- **Drop the CRM Deal and Project `custom_master_*` fields.**
  - Register `ivm.deployments.patches.drop_project_custom_master_customer` in `ivm/patches.txt`. It copies remaining `Project.custom_master_customer` into `partner_customer` (skipping rows where it equals the Project's `customer`), then drops the field and column. It was deliberately not registered in deploy 1 because `partner_customer` does not exist at patch time on prod.
  - Also drop CRM Deal `custom_master_customer` / `custom_master_organization`. Prod has 0 values in both.
- **Remove the `ivm/customer_consolidation/` package and the `iCorp Client Link` review fields** once the consolidation is complete and no longer needed.

---

## Re-Won duplicate guard keys on `project_name`

**Where to look first:** `ivm/deployments/services/provision_project_from_deal.py::_create_project_for_location`. A re-Won deal is guarded by `custom_crm_deal` plus the generated `project_name` (`f"{site_name} - {deal name}"`).

**Gap:** Project has no field linking it to its Deployment Location. If the location name or the deal's HubSpot name changes, the generated name changes and the guard is bypassed.

**Proper fix:** add a real Project → Deployment Location link field and guard on that instead of on `project_name`.

---

## Workspace / Desktop Icon / Workspace Sidebar fixtures use name allowlists

**Context:** `ivm/hooks.py` `fixtures` filters for `Workspace`, `Desktop Icon`, and `Workspace Sidebar` are name allowlists. A new workspace or desktop icon is not exported or synced until its name is added to those lists in `hooks.py`.
