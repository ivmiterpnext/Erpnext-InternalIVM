"""Services for resolving which iCorp clients a Deployment Project may attach to.

A Customer may have multiple of its own iCorp clients (e.g. locations, or
machine-type splits such as "Pfizer" / "Pfizer - Lockers"). A Customer may also
act as a partner that manages OTHER Customers' iCorp clients (the client's
iCorp parent_client belongs to this Customer, but the client itself is
assigned to a different, end Customer).
"""

import re

import frappe
from frappe import _


def require_desk_customer_access() -> None:
	"""Allow only Desk (System) users who can read Customer or Project.

	Guest and Website (portal) users are always denied. The Project and Customer forms are
	used by Projects roles, which can read Projects but not Customers, so either permission
	is enough. Internal callers (provisioning, validation) use the unchecked helpers below.
	"""
	user = frappe.session.user
	if user == "Guest" or frappe.get_cached_value("User", user, "user_type") != "System User":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not (frappe.has_permission("Customer", "read") or frappe.has_permission("Project", "read")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def get_deployable_clients(customer: str | None = None) -> list[dict]:
	"""Whitelisted: the iCorp clients a Customer may deploy under (see _deployable_clients)."""
	require_desk_customer_access()
	return _deployable_clients(customer)


def _deployable_clients(customer: str | None = None) -> list[dict]:
	"""Return active iCorp Client Links deployable for this Customer: its own
	clients (customer == customer) plus clients it manages as a partner
	(parent_client's customer == customer, but the client's own customer is
	set and different). Own clients first, then managed, each group sorted
	by client_name.

	Each row: name, display_label, client_name, customer (the END customer
	for managed rows), partner_customer (the managing partner's Customer,
	derived from this client's own iCorp parent_client -- same logic as
	derive_partner -- computed for BOTH groups so the UI can populate the
	Partner field immediately on selection, not only after save),
	partner_icorp_client_id (that parent_client's own id, when there is a partner; None otherwise), group
	('own'|'managed').
	"""
	if not customer:
		return []

	own = frappe.db.sql(
		"""
		select c.name, c.display_label, c.client_name, c.customer, c.parent_client,
		       case
		         when p.customer is not null and p.customer != '' and p.customer != c.customer
		         then p.customer
		         else null
		       end as partner_customer
		from `tabiCorp Client Link` c
		left join `tabiCorp Client Link` p on p.name = c.parent_client
		where c.customer = %(customer)s
		  and c.is_active = 1
		order by c.client_name
		""",
		{"customer": customer},
		as_dict=True,
	)
	for row in own:
		row["group"] = "own"
		row["partner_icorp_client_id"] = row["parent_client"] if row["partner_customer"] else None

	managed = frappe.db.sql(
		"""
		select c.name, c.display_label, c.client_name, c.customer, c.parent_client, 'managed' as `group`
		from `tabiCorp Client Link` c
		inner join `tabiCorp Client Link` p on p.name = c.parent_client
		where p.customer = %(customer)s
		  and c.is_active = 1
		  and c.customer is not null and c.customer != ''
		  and c.customer != %(customer)s
		order by c.client_name
		""",
		{"customer": customer},
		as_dict=True,
	)
	for row in managed:
		row["partner_customer"] = customer
		row["partner_icorp_client_id"] = row.get("parent_client")

	return own + managed


@frappe.whitelist()
def get_customer_client_summary(customer: str | None = None) -> dict:
	"""Whitelisted: see _customer_client_summary."""
	require_desk_customer_access()
	return _customer_client_summary(customer)


def _customer_client_summary(customer: str | None = None) -> dict:
	"""Report which iCorp Client Links this Customer owns (customer == customer),
	split by is_active. Used to explain why _deployable_clients() is empty:
	inactive-only (reactivate in iCorp) vs no client at all.

	Returns {"active": [link ids], "inactive": [link ids]}, both sorted by id.
	"""
	if not customer:
		return {"active": [], "inactive": []}

	rows = frappe.get_all(
		"iCorp Client Link",
		filters={"customer": customer},
		fields=["name", "is_active"],
		order_by="name asc",
	)
	return {
		"active": [r.name for r in rows if r.is_active],
		"inactive": [r.name for r in rows if not r.is_active],
	}


@frappe.whitelist()
def deployable_client_query(doctype, txt, searchfield, start, page_len, filters):
	"""set_query source for Project.icorp_client_id and the per-row
	icorp_client_id fields on the machine detail child tables.

	filters: {"customer": <Customer name>, "own_only": 0|1 (optional)}
	"""
	require_desk_customer_access()
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	customer = filters.get("customer")
	own_only = filters.get("own_only")

	if not customer:
		return []

	rows = _deployable_clients(customer)
	if own_only:
		rows = [r for r in rows if r["group"] == "own"]

	needle = (txt or "").strip().lower()
	out = []
	for r in rows:
		haystack = f"{r['name']} {r['client_name'] or ''} {r['customer'] or ''}".lower()
		if needle and needle not in haystack:
			continue
		# Frappe renders the first tuple element (the ID) as the bold dropdown
		# title and this description as the subtitle. iCorp Client Link has
		# show_title_field_in_link=0, so the field itself displays the bare ID.
		description = (
			r["client_name"] if r["group"] == "own" else f"{r['client_name']} — Managed · {r['customer']}"
		)
		out.append((r["name"], description))

	start = int(start or 0)
	page_len = int(page_len or 20)
	return out[start : start + page_len]


def derive_partner(icorp_client_id: str | None) -> str | None:
	"""Return the Customer of icorp_client_id's iCorp parent_client, if that
	Customer is set and differs from the client's own Customer. Otherwise None."""
	if not icorp_client_id:
		return None

	row = frappe.db.get_value(
		"iCorp Client Link", icorp_client_id, ["customer", "parent_client"], as_dict=True
	)
	if not row or not row.parent_client:
		return None

	parent_customer = frappe.db.get_value("iCorp Client Link", row.parent_client, "customer")
	if parent_customer and parent_customer != row.customer:
		return parent_customer
	return None


def derive_partner_client(icorp_client_id: str | None) -> str | None:
	"""Return the specific iCorp Client Link id that is icorp_client_id's parent_client,
	but only when that parent represents a real partner relationship (its Customer
	differs from icorp_client_id's own Customer) -- i.e. only when derive_partner()
	would also return something for this same icorp_client_id. None otherwise."""
	if not icorp_client_id:
		return None

	row = frappe.db.get_value(
		"iCorp Client Link", icorp_client_id, ["customer", "parent_client"], as_dict=True
	)
	if not row or not row.parent_client:
		return None

	parent_customer = frappe.db.get_value("iCorp Client Link", row.parent_client, "customer")
	if parent_customer and parent_customer != row.customer:
		return row.parent_client
	return None


_MASTER_SUFFIX_RE = re.compile(r"^(.*?)\s*\(\s*Master:?\s*(\d+)\s*\)\s*$", re.IGNORECASE)


def parse_project_client_ids(raw_value: str | None) -> dict:
	"""Parse a legacy Project.client_id free-text string.

	Returns {"primary": str|None, "others": list[str], "master": str|None, "status": str}.
	status is one of: "empty", "single", "multi", "master_suffix",
	"multi_master_suffix", "malformed".
	"""
	if not raw_value or not str(raw_value).strip():
		return {"primary": None, "others": [], "master": None, "status": "empty"}

	s = str(raw_value).strip()
	master = None

	match = _MASTER_SUFFIX_RE.match(s)
	if match:
		s = match.group(1).strip()
		master = match.group(2)

	ids = [p.strip() for p in re.split(r"[,/]", s) if p.strip()]
	if not ids or not all(i.isdigit() for i in ids):
		return {"primary": None, "others": [], "master": master, "status": "malformed"}

	primary, others = ids[0], ids[1:]
	if master and others:
		status = "multi_master_suffix"
	elif master:
		status = "master_suffix"
	elif others:
		status = "multi"
	else:
		status = "single"

	return {"primary": primary, "others": others, "master": master, "status": status}
