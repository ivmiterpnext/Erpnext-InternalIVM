"""
Backfill CRM Deals, Contacts, and CRM Organizations from HubSpot.

Fetches all HubSpot deals with createdDate >= 2026-01-01 and syncs them
into Frappe CRM. For deals already Won in HubSpot:
  - Does NOT trigger the on_update win logic (Customer provisioning,
    Project creation). Status is written via frappe.db.set_value after insert.
  - Resolves custom_customer via the same CRM Organization-based model
    customer_resolution.py uses for live deals (resolve_deal_customer ->
    apply_deal_customer). Invoked directly because this patch bypasses
    on_update hooks. Unresolved deals are left blank with a warning.

Registered in patches.txt (post_model_sync, end of file) — runs automatically
on migrate. Can also be run manually via:
    bench --site <site> execute \
        "ivm.integrations.hubspot.patches.backfill_deals_from_hubspot.execute"

If a HubSpot rate limit is hit mid-run, the run stops early and returns
normally (does not raise) — check Error Log and re-run manually to resume.
Already-synced deals are skipped on re-run.
"""

from __future__ import annotations

import frappe

from ivm.integrations.hubspot import api, customer_resolution
from ivm.integrations.hubspot.constants import (
	DEAL_FIELD_MAP,
	DEALSTAGE_TO_STATUS,
	HUBSPOT_DEAL_ID_FIELD,
)
from ivm.integrations.hubspot.deal_handler import (
	DEAL_TRANSFORMS,
	_sync_contacts,
	_sync_organization,
)
from ivm.integrations.hubspot.sync_utils import apply_field_map, lookup_or_create, save_doc

_SINCE_DATE = "2026-01-01"
_PROPERTIES = list(DEAL_FIELD_MAP.keys())


def execute() -> None:
	previous_user = frappe.session.user
	frappe.set_user("hubspot@ivm.local")
	try:
		print(f"Fetching HubSpot deals created since {_SINCE_DATE}...")
		hs_deals = _fetch_hubspot_deals(_SINCE_DATE)
		print(f"Found {len(hs_deals)} deal(s) to process.")

		created = skipped = errors = 0

		for idx, hs_deal in enumerate(hs_deals, start=1):
			hs_id = str(hs_deal["id"])
			try:
				was_created = _sync_one_deal(hs_id, hs_deal["properties"])
				if was_created:
					created += 1
				else:
					skipped += 1
			except api.HubSpotRateLimitExhausted as exc:
				print(
					f"  Rate limit hit at deal {idx}/{len(hs_deals)} "
					f"(retry after {exc.retry_after_seconds}s). Stopping early — re-run to resume."
				)
				frappe.log_error(
					title="Backfill: HubSpot rate limit exhausted — stopped early",
					message=(
						f"Processed {idx - 1}/{len(hs_deals)} deals before rate limit. "
						f"Created: {created}, Skipped: {skipped}, Errors: {errors}. "
						f"Re-run the patch to resume — already-synced deals will be skipped."
					),
				)
				break
			except Exception:
				errors += 1
				frappe.log_error(
					title=f"Backfill: failed to sync HubSpot deal {hs_id}",
					message=frappe.get_traceback(with_context=True),
				)
				print(f"  ERROR: deal {hs_id} — see Error Log")

		frappe.db.commit()
		print(f"\nDone. Created: {created}, Skipped (already existed): {skipped}, Errors: {errors}")
	finally:
		frappe.set_user(previous_user)


def _fetch_hubspot_deals(since_date: str) -> list[dict]:
	"""Page through HubSpot search results and return all matching deals."""
	filters = [
		{
			"propertyName": "createdate",
			"operator": "GTE",
			"value": f"{since_date}T00:00:00.000Z",
		}
	]

	results = []
	after = None

	while True:
		try:
			response = api.search_deals(filters=filters, properties=_PROPERTIES, after=after)
		except api.HubSpotRateLimitExhausted as exc:
			print(
				f"  Rate limit hit while fetching deal list "
				f"(retry after {exc.retry_after_seconds}s). "
				f"Returning {len(results)} deal(s) fetched so far — re-run to resume."
			)
			frappe.log_error(
				title="Backfill: HubSpot rate limit exhausted during deal fetch",
				message=f"Fetched {len(results)} deal(s) before rate limit. Re-run the patch to resume.",
			)
			break

		results.extend(response.get("results", []))
		next_page = response.get("paging", {}).get("next", {})
		after = next_page.get("after")
		if not after:
			break

	return results


def _sync_one_deal(hs_id: str, properties: dict) -> bool:
	"""Sync a single HubSpot deal. Returns True if a new CRM Deal was created."""
	raw_stage = properties.get("dealstage") or ""
	real_status = DEALSTAGE_TO_STATUS.get(raw_stage, "Discovery")
	is_won = real_status == "Won"

	# Insert new deals with status="Discovery" so that on_update's
	# has_value_changed("status") check returns False when we later save
	# deal fields — preventing win logic from firing on new Won deals.
	doc, is_new = lookup_or_create(
		doctype="CRM Deal",
		hubspot_id_field=HUBSPOT_DEAL_ID_FIELD,
		hubspot_id=hs_id,
		defaults={"status": "Discovery"},
	)

	# Org must be linked before deal fields are saved (same order as live sync).
	primary_company_id, _master_company_id = api.get_deal_company_ids_by_role(hs_id)
	_sync_organization(hs_id, doc.name, primary_company_id)
	_sync_contacts(hs_id, doc.name)

	# Sync all deal fields except status — status is written via db.set_value below.
	_sync_deal_fields_no_win(doc.name, properties)

	# Write real status directly to DB — does not fire document events.
	current_db_status = frappe.db.get_value("CRM Deal", doc.name, "status")
	if current_db_status != real_status:
		frappe.db.set_value("CRM Deal", doc.name, "status", real_status)

	if is_won:
		_ensure_customer_linked(doc.name)

	return is_new


def _sync_deal_fields_no_win(crm_deal_name: str, properties: dict) -> None:
	"""Sync deal fields, excluding status.

	Status is excluded so that save_doc() cannot trigger on_update win logic
	via has_value_changed("status"). Status is written separately via db.set_value.
	"""
	deal = frappe.get_doc("CRM Deal", crm_deal_name)

	field_map_no_status = {k: v for k, v in DEAL_FIELD_MAP.items() if v != "status"}
	transforms_no_status = {k: v for k, v in DEAL_TRANSFORMS.items() if k != "status"}

	apply_field_map(deal, properties, field_map_no_status, transforms_no_status)
	save_doc(deal, "deal")


def _ensure_customer_linked(crm_deal_name: str) -> None:
	"""Resolve and apply custom_customer for a Won deal via the same org-based model
	customer_resolution.py uses for live deals, invoked directly since this patch
	deliberately bypasses on_update hooks (see module docstring)."""
	existing = frappe.db.get_value("CRM Deal", crm_deal_name, "custom_customer")
	if existing and frappe.db.exists("Customer", existing):
		return

	organization = frappe.db.get_value("CRM Deal", crm_deal_name, "organization")
	# resolve_deal_customer uses attribute access (deal.name / deal.organization),
	# so pass a _dict rather than a plain dict.
	customer_name = customer_resolution.resolve_deal_customer(
		frappe._dict(name=crm_deal_name, custom_customer=existing, organization=organization)
	)

	if customer_name:
		customer_resolution.apply_deal_customer(crm_deal_name, customer_name)
		print(f"  Linked Customer '{customer_name}' to Won deal {crm_deal_name}")
	else:
		print(
			f"  WARNING: Won deal {crm_deal_name} — could not resolve Customer "
			f"via organization (organization={organization or 'none'}). Set custom_customer manually."
		)
