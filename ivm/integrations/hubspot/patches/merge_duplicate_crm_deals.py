"""One-off data fix: merge duplicate CRM Deal records that share the same
HubSpot deal ID.

Caused by a race in the pre-collapse webhook handlers (object.creation and
object.propertyChange could each create their own CRM Deal for the same
HubSpot deal before either one committed) combined with
custom_hubspot_deal_id having no unique constraint. Registered in
patches.txt (post_model_sync) so it runs before the unique index is applied
via sync_customizations — see ivm/ivm/custom/crm_deal.json.

For each HubSpot deal ID with more than one CRM Deal row:
  1. Pick a survivor (most Projects, then most-recently-set custom_customer
     preference, then most Deployment Locations, then most linked records
     overall, then earliest creation).
  2. Merge every other row into the survivor via frappe.rename_doc(...,
     merge=True), which re-points every Link and Dynamic Link field
     (Deployment Location.crm_deal, Project.custom_crm_deal, FCRM Note,
     CRM Task, CRM Call Log, Communication, File attachments) onto the
     survivor and deletes the loser.
  3. Deduplicate Files left with an identical file_name on the survivor.

A group is skipped (not merged) and causes the whole patch to raise after
all groups are processed if: more than one row in the group has a linked
Project, or the group has more than one distinct non-empty custom_customer
value. Prod and dev data checked before this patch was written have no such
conflicts — if one appears, it means something unexpected (e.g. a Won deal
duplicated after provisioning) and needs a human to pick the right survivor
by hand rather than have this patch guess.

Raising aborts bench migrate before the unique index is ever applied, so a
genuinely conflicting site fails loudly instead of silently corrupting data
or crashing later on the index creation with a less informative error.

Re-running this patch is safe: once a HubSpot ID's rows are merged down to
one, it no longer appears in the duplicate-group query.
"""

from __future__ import annotations

import frappe
from frappe.model.rename_doc import rename_doc

from ivm.integrations.hubspot.constants import DEAL_TYPE_ID, HUBSPOT_DEAL_ID_FIELD
from ivm.integrations.hubspot.sync_utils import enqueue_sync

# frappe.rename_doc (the public frappe/__init__.py wrapper) does not accept
# ignore_permissions — its signature only forwards force/merge/ignore_if_exists/
# show_alert/rebuild_search to the real implementation, hardcoding
# ignore_permissions=False. Import the real frappe.model.rename_doc.rename_doc
# directly so we can pass ignore_permissions=True for this unattended migrate-time
# merge (this always runs as Administrator during `bench migrate`, which already
# bypasses permission checks, but passing it explicitly avoids depending on that).

_LINKED_RECORD_QUERIES = (
	("Project", {"custom_crm_deal": None}),
	("Deployment Location", {"crm_deal": None}),
	("FCRM Note", {"reference_doctype": "CRM Deal", "reference_docname": None}),
	("CRM Task", {"reference_doctype": "CRM Deal", "reference_docname": None}),
	("CRM Call Log", {"reference_doctype": "CRM Deal", "reference_docname": None}),
	("Communication", {"reference_doctype": "CRM Deal", "reference_name": None}),
	("File", {"attached_to_doctype": "CRM Deal", "attached_to_name": None}),
	("CRM Contacts", {"parenttype": "CRM Deal", "parent": None}),
)


def execute() -> None:
	_clear_empty_hubspot_ids()

	groups = _find_duplicate_groups()
	if not groups:
		return

	print(f"Found {len(groups)} duplicate HubSpot deal ID(s) to merge.")

	failed: list[str] = []

	for hs_id, names in groups.items():
		savepoint = f"merge_dup_deal_{hs_id}".replace("-", "_").replace(".", "_")
		frappe.db.savepoint(savepoint)
		try:
			_merge_group(hs_id, names)
		except Exception:
			frappe.db.rollback(save_point=savepoint)
			failed.append(hs_id)
			frappe.log_error(
				title=f"Duplicate CRM Deal merge failed: HubSpot deal {hs_id}",
				message=f"rows={names}\n\n{frappe.get_traceback(with_context=True)}",
			)

	remaining = _find_duplicate_groups()
	if remaining:
		failed = sorted(set(failed) | set(remaining.keys()))

	if failed:
		frappe.db.rollback()
		raise RuntimeError(
			f"merge_duplicate_crm_deals: {len(failed)} HubSpot deal ID(s) could not be "
			f"fully merged and still have duplicate CRM Deal rows: {failed}. "
			f"Check the Error Log for each one (title starts with "
			f"'Duplicate CRM Deal merge'), resolve by hand, then re-run this patch "
			f"(bench --site <site> migrate, or execute this patch's `execute()` directly)."
		)

	frappe.db.commit()

	for hs_id in groups:
		enqueue_sync(
			"ivm.integrations.hubspot.deal_handler.sync_deal",
			DEAL_TYPE_ID,
			hs_id,
			hubspot_deal_id=hs_id,
		)

	print(f"Merged {len(groups)} duplicate HubSpot deal ID(s). Re-sync enqueued for each.")


def _clear_empty_hubspot_ids() -> None:
	"""Blank custom_hubspot_deal_id values become NULL so the upcoming unique
	index (applied separately via sync_customizations) doesn't collide on
	multiple empty strings. Frappe already treats blank unique-field values
	as NULL on save, this just applies that same rule to any rows that
	predate the unique flag.
	"""
	frappe.db.sql(
		f"""
		UPDATE `tabCRM Deal`
		SET {HUBSPOT_DEAL_ID_FIELD} = NULL
		WHERE {HUBSPOT_DEAL_ID_FIELD} = ''
		"""
	)


def _find_duplicate_groups() -> dict[str, list[str]]:
	"""Return {hubspot_deal_id: [crm_deal_name, ...]} for every HubSpot ID
	with more than one CRM Deal row, ordered by creation (oldest first).
	"""
	rows = frappe.db.sql(
		f"""
		SELECT {HUBSPOT_DEAL_ID_FIELD} AS hubspot_deal_id, name
		FROM `tabCRM Deal`
		WHERE {HUBSPOT_DEAL_ID_FIELD} IS NOT NULL AND {HUBSPOT_DEAL_ID_FIELD} != ''
		ORDER BY creation ASC
		""",
		as_dict=True,
	)
	groups: dict[str, list[str]] = {}
	for row in rows:
		groups.setdefault(row.hubspot_deal_id, []).append(row.name)
	return {hs_id: names for hs_id, names in groups.items() if len(names) > 1}


def _merge_group(hs_id: str, names: list[str]) -> None:
	facts = {name: _gather_facts(name) for name in names}

	project_rows = [n for n in names if facts[n]["project_count"] > 0]
	customers = {facts[n]["custom_customer"] for n in names if facts[n]["custom_customer"]}

	if len(project_rows) > 1:
		raise RuntimeError(
			f"HubSpot deal {hs_id}: more than one row has a linked Project ({project_rows}) — "
			f"cannot auto-merge, needs manual review"
		)
	if len(customers) > 1:
		raise RuntimeError(
			f"HubSpot deal {hs_id}: rows disagree on custom_customer ({customers}) — "
			f"cannot auto-merge, needs manual review"
		)

	survivor = _pick_survivor(names, facts)
	losers = [n for n in names if n != survivor]

	for loser in losers:
		rename_doc(
			doctype="CRM Deal",
			old=loser,
			new=survivor,
			merge=True,
			force=True,
			ignore_permissions=True,
			rebuild_search=False,
			show_alert=False,
		)

	_dedupe_survivor_files(survivor)


def _gather_facts(name: str) -> dict:
	return {
		"project_count": frappe.db.count("Project", {"custom_crm_deal": name}),
		"location_count": frappe.db.count("Deployment Location", {"crm_deal": name}),
		"custom_customer": frappe.db.get_value("CRM Deal", name, "custom_customer") or "",
		"linked_total": _linked_total(name),
	}


def _linked_total(name: str) -> int:
	total = 0
	for doctype, base_filters in _LINKED_RECORD_QUERIES:
		filters = dict(base_filters)
		# Replace the single None placeholder with this deal's name.
		key = next(k for k, v in filters.items() if v is None)
		filters[key] = name
		total += frappe.db.count(doctype, filters)
	return total


def _pick_survivor(names: list[str], facts: dict[str, dict]) -> str:
	"""names is already ordered oldest-first. Sort key: most Projects, then
	has a custom_customer set, then most Deployment Locations, then most
	linked records overall, then earliest creation (preserved by stable
	sort over the already creation-ordered input).
	"""

	def sort_key(name: str) -> tuple:
		f = facts[name]
		return (
			-f["project_count"],
			-(1 if f["custom_customer"] else 0),
			-f["location_count"],
			-f["linked_total"],
		)

	return sorted(names, key=sort_key)[0]


def _dedupe_survivor_files(survivor: str) -> None:
	"""After a merge, the survivor may have two File rows with the same
	file_name (both sides had independently synced the same HubSpot
	attachment). Keep the oldest, delete the rest.
	"""
	rows = frappe.db.sql(
		"""
		SELECT name, file_name, creation
		FROM `tabFile`
		WHERE attached_to_doctype = 'CRM Deal' AND attached_to_name = %(survivor)s
		ORDER BY file_name, creation ASC
		""",
		{"survivor": survivor},
		as_dict=True,
	)
	seen: set[str] = set()
	for row in rows:
		if row.file_name in seen:
			frappe.delete_doc("File", row.name, ignore_permissions=True, force=True)
		else:
			seen.add(row.file_name)
