# Copilot Instructions for MSSQL Frappe

## Project Overview
- **Purpose:** Integrates Microsoft SQL Server with the Frappe framework, enabling data sync and API access between Frappe and external MSSQL-backed services.
- **Structure:**
  - `mssql_frappe/` (main app code)
    - `api/` – API endpoints and integrations
    - `utils/` – Utility modules (data, case, filter, cache, sync)
    - `link/` – Query and linking logic for Frappe doctypes
    - `mssql_frappe/doctype/` – Custom Frappe doctypes (business objects)
    - `patches/` – Migration and patch scripts
    - `public/` – Static assets (JS, CSS)
    - `templates/` – Jinja templates for web pages
    - `hooks.py` – Frappe app configuration and event hooks

## Key Patterns & Conventions
- **API Integration:**
  - External APIs (e.g., Azure, ICorp, Headwind) accessed via utility functions in `utils/api_utils.py`.
  - Secrets and credentials are fetched from Azure Key Vault using `DefaultAzureCredential`.
  - Data transformation helpers: `dict_keys_to_snake_case`, `dict_keys_to_camel_case` in `utils/case_utils.py`.
- **Frappe Doctypes:**
  - Custom business logic is implemented in `mssql_frappe/doctype/<doctype>/<doctype>.py`.
  - Use `@frappe.whitelist()` for functions exposed to the Frappe API.
  - Linking and search logic is centralized in `link/query.py`.
- **Filtering & Querying:**
  - Use helpers in `utils/filter_utils.py` for converting filters to query params and regex matching.
- **Code Style & Linting:**
  - Enforced via `pre-commit` (see `.pre-commit-config.yaml`).
  - Python: `ruff`, `pyupgrade`.
  - JS: `eslint`, `prettier`.
  - Run `pre-commit install` after cloning.
- **Build & Install:**
  - Install via Frappe Bench CLI: `bench get-app ...`, `bench install-app mssql_frappe`.
  - Python dependencies managed in `pyproject.toml` (Frappe itself managed by Bench).

## Developer Workflows
- **Testing:**
  - Tests for doctypes are in `mssql_frappe/doctype/<doctype>/test_<doctype>.py`.
  - No global test runner defined; use Frappe's test utilities or run test files directly.
- **Debugging:**
  - Use Frappe's logging (`frappe.log_error`) for error reporting in API and link modules.
- **Patches & Migrations:**
  - Place migration scripts in `patches/`.
  - Use Frappe's patch execution for DB/data migrations.

## Integration Points
- **External Services:**
  - Azure Key Vault, ICorp API, Headwind API (see `utils/api_utils.py`).
  - All credentials/secrets should be accessed via environment variables or Key Vault.
- **Frappe Framework:**
  - App hooks and configuration in `hooks.py`.
  - Custom doctypes registered under `mssql_frappe/doctype/`.

## Examples
- **API Call:** See `utils/api_utils.py` for Azure/ICorp token handling and request patterns.
- **Doctype Logic:** See `mssql_frappe/doctype/machine_address/machine_address.py` for custom business logic.
- **Link/Search:** See `link/query.py` for search and linking functions using Frappe ORM.

---

For questions or unclear conventions, review `README.md`, `hooks.py`, and utility modules. Ask for clarification if a workflow or pattern is not documented here.
