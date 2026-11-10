"""Read-only impact analysis for a planned Customer merge: what Frappe's merge mechanism
would move, what it wouldn't catch (duplicate contacts/addresses, field values only set on
the losing record, and genuine field-value conflicts needing a human decision), and what
iCorp clients sit on each side — to help fill in a merge row's `merge_considerations` and
`field_resolutions` columns before anything is actually merged.
"""

import re

import frappe
from frappe.model import no_value_fields, table_fields
from frappe.model.rename_doc import get_link_fields

from ivm.customer_consolidation.decisions import parse_field_resolutions

_SKIP_FIELDS = frozenset(
	{
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"naming_series",
		"customer_name",
		"lft",
		"rgt",
		"old_parent",
		"_user_tags",
		"_comments",
		"_assign",
		"_liked_by",
		# Enabled/disabled state is owned by the disposition/disable workflow, never by a merge. Without
		# this, a disabled loser merged into an active survivor shows up as "disabled: '1'" in
		# fields_to_copy (0 counts as blank for numeric fields) and silently disables the survivor.
		"disabled",
	}
)

# For these fieldtypes, "0" (or "0.0") means "never set", not a deliberate value worth flagging
# as a conflict or copying over.
_NUMERIC_FIELDTYPES = frozenset({"Int", "Float", "Currency", "Percent"})
_BLANK_NUMERIC_STRINGS = frozenset({"0", "0.0"})

# Fields where a real difference between the two sides still isn't worth blocking a merge over.
# Still eligible to be copied if the survivor's side is blank; only suppressed as a *conflict*.
# `industry` is ignored because the survivor's industry is typically more accurate. `customer_primary_contact`
# is ignored the same way — the survivor always keeps its own contact; the merged Customer's contacts still
# move over via the normal link-repointing.
IGNORED_CONFLICT_FIELDS = frozenset({"industry", "customer_primary_contact"})

# Fields describing our side of the relationship (ownership/sales metadata), not the company's
# identity. Safe to auto-resolve to the survivor's value when every member of a duplicate group
# has zero operational links (see orphan_customers.classify_customer) -- see disposition.py.
SOFT_RESOLVE_FIELDS = frozenset(
	{
		"account_owner",
		"account_manager",
		"customer_type",
		"customer_group",
		"territory",
		"language",
		"account_record_type",
		"ownership",
		"default_currency",
		"lead_name",
		"opportunity_name",
	}
)


def _as_number(value_str: str) -> float | None:
	"""Parse a value as a plain number (commas allowed as thousands separators). None if it isn't
	numeric-looking at all."""
	if not value_str:
		return None
	try:
		return float(value_str.replace(",", ""))
	except ValueError:
		return None


def normalize_text(value: str | None) -> str:
	"""Lowercase, keep only [a-z0-9] characters."""
	return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def find_possible_duplicate_contacts(from_contacts: list[dict], into_contacts: list[dict]) -> list[str]:
	"""Each contact dict: {"name", "first_name", "last_name", "email_id"}. Flag a pair if the emails
	match, the full names match once normalized, or the first three letters of the first name match
	and the normalized last names match or one is a prefix of the other."""
	results = []

	for a in from_contacts:
		a_email = (a.get("email_id") or "").strip().lower()
		a_full = normalize_text((a.get("first_name") or "") + (a.get("last_name") or ""))
		a_first3 = normalize_text(a.get("first_name"))[:3]
		a_last = normalize_text(a.get("last_name"))

		for b in into_contacts:
			b_email = (b.get("email_id") or "").strip().lower()
			b_full = normalize_text((b.get("first_name") or "") + (b.get("last_name") or ""))
			b_first3 = normalize_text(b.get("first_name"))[:3]
			b_last = normalize_text(b.get("last_name"))

			is_duplicate = False
			if a_email and b_email and a_email == b_email:
				is_duplicate = True
			elif a_full and b_full and a_full == b_full:
				is_duplicate = True
			elif (
				a_first3
				and b_first3
				and a_first3 == b_first3
				and a_last
				and b_last
				and (a_last == b_last or a_last.startswith(b_last) or b_last.startswith(a_last))
			):
				is_duplicate = True

			if is_duplicate:
				results.append(f"{a['name']} <-> {b['name']}")

	return results


def find_possible_duplicate_addresses(from_addresses: list[dict], into_addresses: list[dict]) -> list[str]:
	"""Each address dict: {"name", "address_line1", "city", "address_type"}. Flag a pair if the
	normalized address line and city both match."""
	results = []

	for a in from_addresses:
		a_line = normalize_text(a.get("address_line1"))
		a_city = normalize_text(a.get("city"))

		for b in into_addresses:
			b_line = normalize_text(b.get("address_line1"))
			b_city = normalize_text(b.get("city"))

			if a_line and a_line == b_line and a_city == b_city:
				results.append(f"{a['name']} <-> {b['name']}")

	return results


def _is_blank_value(value_str: str, fieldtype: str) -> bool:
	"""A value counts as blank if it's empty, or — for numeric fieldtypes — if it's just the
	unset default (0 / 0.0), which isn't real data worth copying or flagging as a conflict."""
	if value_str == "":
		return True
	if fieldtype in _NUMERIC_FIELDTYPES and value_str in _BLANK_NUMERIC_STRINGS:
		return True
	return False


def diff_customer_values(from_values: dict, into_values: dict, fieldname_types: dict[str, str]) -> dict:
	"""Split field differences into two kinds:
	- fields_to_copy: the losing record has real data, the survivor has none — safe to carry over
	  automatically, no decision needed.
	- fields_in_conflict: both sides have real, different data — needs a human decision (see
	  parse_field_resolutions / the customer_merges.csv `field_resolutions` column).

	For any field where BOTH sides parse as plain numbers, 0 counts as blank regardless of the
	stored fieldtype — several "total_*" fields are stored as Data/Text but are still just an
	unset numeric default at 0, not a real value worth flagging or preserving.

	Fields in IGNORED_CONFLICT_FIELDS never produce a conflict entry (the survivor's value is kept
	as-is), but are still eligible for fields_to_copy if the survivor's side is blank.

	Returns {"fields_to_copy": list[str], "fields_in_conflict": list[str]}.
	"""
	fields_to_copy = []
	fields_in_conflict = []

	for fieldname, fieldtype in fieldname_types.items():
		from_value = from_values.get(fieldname)
		into_value = into_values.get(fieldname)
		from_str = str(from_value).strip() if from_value not in (None, "") else ""
		into_str = str(into_value).strip() if into_value not in (None, "") else ""

		from_num = _as_number(from_str)
		into_num = _as_number(into_str)
		both_numeric = from_num is not None and into_num is not None

		from_blank = _is_blank_value(from_str, fieldtype) or (both_numeric and from_num == 0)
		into_blank = _is_blank_value(into_str, fieldtype) or (both_numeric and into_num == 0)

		if from_blank or from_str == into_str:
			continue

		if into_blank:
			fields_to_copy.append(f"{fieldname}: '{from_str}'")
		elif fieldname in IGNORED_CONFLICT_FIELDS:
			continue
		else:
			fields_in_conflict.append(f"{fieldname}: into='{into_str}' vs from='{from_str}'")

	return {"fields_to_copy": fields_to_copy, "fields_in_conflict": fields_in_conflict}


def find_unresolved_field_conflicts(
	fields_in_conflict: list[str], field_resolutions: dict[str, str]
) -> list[str]:
	"""Of the detected field conflicts, return the ones with no decision recorded yet in
	field_resolutions (a conflict entry looks like "fieldname: into='...' vs from='...'")."""
	unresolved = []
	for entry in fields_in_conflict:
		fieldname = entry.split(":", 1)[0].strip()
		if fieldname not in field_resolutions:
			unresolved.append(entry)
	return unresolved


def get_customer_field_types() -> dict[str, str]:
	"""Customer fields worth comparing between a merge's two sides, mapped to their fieldtype (needed
	to tell a real numeric value apart from an unset 0). Excludes layout/no-value fields, child
	tables, and the always-skipped system fields."""
	meta = frappe.get_meta("Customer")
	field_types = {}

	for field in meta.fields:
		if field.fieldtype in no_value_fields:
			continue
		if field.fieldtype in table_fields:
			continue
		if field.fieldname in _SKIP_FIELDS:
			continue
		field_types[field.fieldname] = field.fieldtype

	return field_types


def get_customer_values(customer: str, fieldnames: list[str]) -> dict:
	return frappe.db.get_value("Customer", customer, fieldnames, as_dict=True) or {}


def get_customer_link_fields() -> list[dict]:
	"""Every non-single Link field across the install that points at Customer — the same list
	Frappe's own rename_doc(merge=True) uses to repoint records."""
	return [f for f in get_link_fields("Customer") if not f.get("issingle")]


def count_linked_records(customer: str, link_fields: list[dict]) -> list[str]:
	"""How many records would move for this Customer, per linked doctype/field, plus Dynamic Link
	rows (Contact/Address) grouped by parent doctype. Only non-zero counts are included."""
	counts = []

	for field in link_fields:
		try:
			n = frappe.db.count(field["parent"], {field["fieldname"]: customer})
			if n:
				counts.append(f"{field['parent']}.{field['fieldname']}:{n}")
		except Exception:
			continue

	try:
		rows = frappe.get_all(
			"Dynamic Link",
			filters={"link_doctype": "Customer", "link_name": customer},
			fields=["parenttype"],
		)
		grouped: dict[str, int] = {}
		for row in rows:
			grouped[row["parenttype"]] = grouped.get(row["parenttype"], 0) + 1
		for parenttype, n in grouped.items():
			counts.append(f"{parenttype} (dynamic link):{n}")
	except Exception:
		pass

	return sorted(counts)


def get_linked_contacts(customer: str) -> list[dict]:
	names = [
		row["parent"]
		for row in frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Contact", "link_doctype": "Customer", "link_name": customer},
			fields=["parent"],
		)
	]
	if not names:
		return []
	return frappe.get_all(
		"Contact", filters={"name": ["in", names]}, fields=["name", "first_name", "last_name", "email_id"]
	)


def get_linked_addresses(customer: str) -> list[dict]:
	names = [
		row["parent"]
		for row in frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Address", "link_doctype": "Customer", "link_name": customer},
			fields=["parent"],
		)
	]
	if not names:
		return []
	return frappe.get_all(
		"Address", filters={"name": ["in", names]}, fields=["name", "address_line1", "city", "address_type"]
	)


def _client_ids_for_customer(coverage_by_customer: dict, customer: str) -> list[str]:
	row = coverage_by_customer.get(customer)
	if not row:
		return []
	ids: list[str] = []
	for key in ("confirmed_client_ids", "single_source_client_ids", "conflicting_client_ids"):
		value = row.get(key, "")
		if value:
			ids.extend(part.strip() for part in value.split(";") if part.strip())
	return sorted(set(ids))


def build_merge_check_rows(validated_merges: list[dict], client_matches_before: list[dict]) -> list[dict]:
	"""For each validated merge row: if it has validation errors, only fill the identifying
	columns. Otherwise, gather everything Frappe's merge wouldn't tell you on its own."""
	from ivm.customer_consolidation.dry_run import build_customer_coverage

	coverage_by_customer = {row["customer"]: row for row in build_customer_coverage(client_matches_before)}
	link_fields = get_customer_link_fields()
	field_types = get_customer_field_types()

	rows = []

	for merge in validated_merges:
		merge_from = merge.get("merge_from", "")
		merge_into = merge.get("merge_into", "")
		resolved_into = merge.get("resolved_into", "")
		errors = merge.get("errors") or []
		status = merge.get("status", "pending")
		evidence = merge.get("evidence", "")
		considerations = merge.get("merge_considerations", "")
		field_resolutions = parse_field_resolutions(merge.get("field_resolutions", ""))

		if status in ("invalid", "already_applied"):
			rows.append(
				{
					"merge_from": merge_from,
					"merge_into": merge_into,
					"resolved_into": resolved_into,
					"status": status,
					"valid": "no" if status == "invalid" else "yes",
					"ready_to_merge": "no",
					"validation_errors": errors,
					"linked_records_from": [],
					"linked_records_into": [],
					"fields_to_copy": [],
					"fields_in_conflict": [],
					"unresolved_field_conflicts": [],
					"contacts_from": [],
					"contacts_into": [],
					"possible_duplicate_contacts": [],
					"addresses_from": [],
					"addresses_into": [],
					"possible_duplicate_addresses": [],
					"icorp_clients_from": [],
					"icorp_clients_into": [],
					"evidence": evidence,
					"merge_considerations": considerations,
				}
			)
			continue

		contacts_from_raw = get_linked_contacts(merge_from)
		contacts_into_raw = get_linked_contacts(merge_into)
		addresses_from_raw = get_linked_addresses(merge_from)
		addresses_into_raw = get_linked_addresses(merge_into)

		field_diff = diff_customer_values(
			get_customer_values(merge_from, list(field_types.keys())),
			get_customer_values(merge_into, list(field_types.keys())),
			field_types,
		)
		unresolved_conflicts = find_unresolved_field_conflicts(
			field_diff["fields_in_conflict"], field_resolutions
		)

		rows.append(
			{
				"merge_from": merge_from,
				"merge_into": merge_into,
				"resolved_into": resolved_into,
				"status": status,
				"valid": "yes",
				"ready_to_merge": "yes" if not unresolved_conflicts else "no",
				"validation_errors": [],
				"linked_records_from": count_linked_records(merge_from, link_fields),
				"linked_records_into": count_linked_records(merge_into, link_fields),
				"fields_to_copy": field_diff["fields_to_copy"],
				"fields_in_conflict": field_diff["fields_in_conflict"],
				"unresolved_field_conflicts": unresolved_conflicts,
				"contacts_from": [
					f"{c['name']} ({c.get('email_id') or 'no email'})" for c in contacts_from_raw
				],
				"contacts_into": [
					f"{c['name']} ({c.get('email_id') or 'no email'})" for c in contacts_into_raw
				],
				"possible_duplicate_contacts": find_possible_duplicate_contacts(
					contacts_from_raw, contacts_into_raw
				),
				"addresses_from": [
					f"{a['name']}: {a.get('address_line1') or ''}, {a.get('city') or ''}"
					for a in addresses_from_raw
				],
				"addresses_into": [
					f"{a['name']}: {a.get('address_line1') or ''}, {a.get('city') or ''}"
					for a in addresses_into_raw
				],
				"possible_duplicate_addresses": find_possible_duplicate_addresses(
					addresses_from_raw, addresses_into_raw
				),
				"icorp_clients_from": _client_ids_for_customer(coverage_by_customer, merge_from),
				"icorp_clients_into": _client_ids_for_customer(coverage_by_customer, merge_into),
				"evidence": evidence,
				"merge_considerations": considerations,
			}
		)

	return rows
