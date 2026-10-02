# Backlog

Known gaps and open questions surfaced during other work (test coverage audits, gotcha investigation, etc.) that weren't in scope to fix at the time. Each entry is written so a fresh agent can pick it up without re-deriving the discovery from scratch — read the listed files first, then the "Open questions" before proposing a fix.

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

## `create_projects_from_deal`'s duplicate-skip only works when `hubspot_site_id` is set

**Where to look first:**
- `ivm/deployments/services/provision_project_from_deal.py::_create_project_for_location` (~line 133):
  ```python
  if location.hubspot_site_id and frappe.db.exists("Project", {"custom_hubspot_deployment_site_id": location.hubspot_site_id}):
      ...
      return None
  ```
- `ivm/deployments/event_handlers/deal.py::on_update` — the only known current caller, invoked when a CRM Deal's `status` changes to `"Won"` (gated by `doc.has_value_changed("status")`, so a normal single Won-transition won't naturally trigger this twice).
- `ivm/deployments/services/tests/test_provision_project_from_deal.py::TestDuplicateSkipByHubspotSiteId::test_no_hubspot_site_id_second_call_hits_duplicate_name` — the test that reproduces this (confirmed via direct reproduction, not speculation, 2026-09-16).

**What's confirmed:**
The dedup check is entirely gated on `location.hubspot_site_id` being truthy. If a Deployment Location has no `hubspot_site_id` (i.e. it was created manually in Frappe rather than synced from HubSpot), a second call to `create_projects_from_deal` for the same CRM Deal attempts to create another Project with an identical, deterministically-derived `project_name` (`f"{site_name} - {deal.get('custom_hubspot_deal_name') or deal.name}"`), which collides with `Project.project_name`'s unique constraint and raises `frappe.UniqueValidationError` instead of skipping gracefully like the `hubspot_site_id`-present path does.

**Open questions for whoever picks this up:**
1. How many existing Deployment Locations in dev/production lack a `hubspot_site_id` (manually created, non-HubSpot-synced)? If that number is non-trivial, this is a live risk, not just a theoretical one.
2. Should the dedup fallback match on `(crm_deal, location_name)` or on the deterministic `project_name` itself when `hubspot_site_id` is absent, rather than only deduping when it's present?
3. Is there any caller today — besides the once-per-Won-transition `on_update` handler — that could invoke `create_projects_from_deal` twice for the same deal (a retry path, a manual "regenerate deployments" action, a bulk migration/backfill script)? Search before assuming this is purely theoretical.

---

## Tier 3 test coverage — untested event handlers & utils in core modules

Next batch of the test-coverage audit (Tier 1 and Tier 2 are done — see `ivm/*/doctype/*/test_*.py` and `ivm/*/services/tests/test_*.py` for established patterns and conventions to follow). Same scope as Tier 2: core operational modules only. `machine_hardware_management` and `ivm/integrations/` remain excluded.

**Files and functions to cover:**

- `ivm/deployments/event_handlers/project.py` — `before_validate`, `validate` (and its private helper `_link_crm_deal`), `after_insert`. (`_update_due_dates` now has focused coverage in `ivm/deployments/event_handlers/tests/test_project.py` — the table-driven due-date logic and its per-field error handling are tested; `before_validate`/`validate`'s status-restore behavior, `_link_crm_deal`, and `after_insert` remain uncovered.)
- `ivm/deployments/event_handlers/deal_notes.py` — `get_notes`, `add_note`, `edit_note`, `delete_note`
- `ivm/warehouse/event_handlers/stock_entry.py` — `after_insert`, `on_submit`
- `ivm/support/event_handlers/communication.py` — `on_update`
- `ivm/support/overrides.py` — `CustomEmailAccount.send_auto_reply`
- `ivm/support/utils.py` — `fetch_customer_name_and_contact`
- `ivm/overrides/realtime_permission.py` — `has_permission`
- `ivm/client_portal/event_handlers/service_quote.py` — `on_submit`
- `ivm/client_portal/utils/home_page.py` — `get_website_user_home_page`
- `ivm/client_portal/utils/notifications.py` — `notify_assigned_rep`

**Known traps from Tier 1/2, worth checking for before assuming a test failure means the code is wrong:**
- Fields with `fetch_from` set (e.g. `Service Quote.sales_representative` ← `crm_deal.deal_owner`) get silently overwritten on save if the source field is empty — check any Link field's JSON for `fetch_from` before asserting on it.
- Some fields that look like booleans are actually Select fields with `"Yes"/"No"` string options (e.g. `Project.coi_required`), not Checkboxes — check `fieldtype`/`options` in the doctype JSON first.
- `before_save`/`before_insert` hooks and Server Scripts can silently rewrite a field you just set — e.g. `ivm.warehouse.event_handlers.item.before_save` auto-adds `item_code` as a barcode on every Item save; two Server Scripts on Warehouse Request overwrite `subject` for any "Build"-containing `request_reason` (see the entry above in this file).
- `frappe.sendmail()` requires a configured outgoing Email Account even in test mode on `test.local` — mock `frappe.sendmail` rather than asserting against a real Email Queue entry.
- Link fields (e.g. `industry` on CRM Organization) require an existing record of that linked doctype, not a freeform string — check `options` on the field before passing an arbitrary value.

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
