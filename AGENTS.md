# AGENTS.md

Agent guide for `apps/ivm` (IVM Frappe app, Frappe 16 stack).

## Scope

- This repository is a Frappe app named `ivm`.
- It is intended to run inside a Bench at `frappe-bench/`.
- Treat Frappe 16 as authoritative for framework behavior and commands.
- Ignore or avoid older Frappe docs when guidance conflicts.
- This app builds on Frappe CRM, ERPNext, and Frappe Wiki.
- It will be added to a Frappe Cloud-hosted site.
- It is intended for an internal company portal use case.
- "Modules" means top-level folders like `client_management`, `support`, etc.

## Working directories

- App root: `apps/ivm`.
- Python package root: `apps/ivm/ivm`.
- Bench root: `frappe-bench` (one level above `apps/`).

## Current repository realities

- Current codebase is scaffold-heavy and minimal.
- Primary enforced standards come from config files:
  - `.editorconfig`
  - `pyproject.toml`
  - `.pre-commit-config.yaml`
  - `.eslintrc`
- Favor these configs over generic style preferences.

## Python style guidelines

- Use Python 3.14-compatible syntax (project target is `py314`).
- Use tabs for indentation (per `.editorconfig` and Ruff format config).
- Prefer double quotes for strings.
- Keep imports at top unless Frappe runtime patterns require local imports.
- Let Ruff sort imports; do not manually fight import order.
- Use snake_case for variables, functions, and module filenames.
- Use PascalCase for classes and DocType controller classes.
- Add type hints for new/changed Python code where practical.
- Prefer explicit types over `Any` unless integration APIs force it.
- Keep functions small and side effects explicit.
- Avoid broad `except Exception` unless immediately re-raised or logged.

## Error handling and logging

- Use `frappe.throw` for user-facing validation/business errors.
- Use specific exception classes when possible.
- Log unexpected failures with useful context (`frappe.log_error`).
- Do not swallow exceptions silently.
- Include enough context to debug, but never secrets.

## Frappe data and permission practices

- Prefer ORM/query builder APIs over raw SQL.
- If raw SQL is unavoidable, parameterize every query.
- Always enforce permissions for reads/writes exposed to users.
- Validate role/permission assumptions in whitelisted methods.
- Avoid N+1 queries; batch using `frappe.get_all` with explicit fields.
- Avoid `fields=["*"]` in hot paths.
- Keep transaction boundaries clear for multi-doc writes.

## Naming and module conventions

- Keep business logic inside the correct top-level module folder.
- Do not create cross-module coupling without clear need.
- Keep naming aligned with DocType names and module boundaries.
- For new modules, follow existing app layout patterns.

## Hooks and framework integration

- Register framework integration points in `ivm/hooks.py`.
- Keep hook handlers importable and lightweight.
- Avoid expensive work at import time in hooks.
- For scheduled/background work, design idempotent job logic.

## Frontend and JS conventions

- JS linting is enforced with ESLint recommended base.
- Many formatting rules are delegated to Prettier.
- Use tabs for indentation in JS/Vue/SCSS/HTML.
- Keep browser-side code compatible with Frappe desk runtime globals.

## Performance and reliability priorities

- Prioritize correctness first, then performance on hot paths.
- Minimize DB round-trips in request handlers and reports.
- Avoid expensive per-row logic inside loops when batch operations exist.
- Prefer predictable, testable code over clever shortcuts.

## Agent workflow expectations

- Keep diffs focused; avoid unrelated refactors.
- Preserve compatibility with CRM, ERPNext, and Wiki integrations.
- Document new operational commands in this file when introduced.
- After every file update, ask for approval before continuing.
- Do not proceed to the next change until approval is received.

## Documentation source policy

- Use Frappe 16 documentation/pages as the source of truth.
- Do not rely on v14/v15 guidance when behavior differs.
- If online docs are mixed-version, prefer commands verified for Frappe 16.
