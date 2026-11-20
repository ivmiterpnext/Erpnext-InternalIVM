"""onload doc_event for Customer: attaches this Customer's iCorp Client Link rows so the form's
icorp_clients_html field can render them without a separate round trip. Read-only; never writes.

Two lists are attached:
  - icorp_clients: Links assigned to this Customer, each with a `relationship` label. For a
    top-level client the label is derived from who its iCorp children are assigned to (this
    Customer = locations, another Customer = managed as a partner, nobody = unassigned), since
    iCorp's is_partner_client flag is unreliable on its own; the flag is appended as a note.
  - icorp_managed_clients: iCorp children of this Customer's Links that are NOT assigned to this
    Customer (assigned elsewhere, or unassigned) — e.g. the end-customer clients a partner like
    World Wide Technologies manages. Read from parent_client; nothing is stored on Customer.
"""

import frappe

from ivm.deployments.services.deployment_clients import derive_partner, derive_partner_client


def _plural(count: int, singular: str, plural: str | None = None) -> str:
	return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def load_icorp_clients(doc, method=None):
	if doc.is_new():
		return

	links = frappe.get_all(
		"iCorp Client Link",
		filters={"customer": doc.name},
		fields=[
			"name",
			"display_label",
			"is_active",
			"parent_client",
			"assignment_source",
			"is_partner_client",
		],
		order_by="is_active desc, client_name asc",
	)

	own_ids = {link["name"] for link in links}
	label_by_id = {link["name"]: link["display_label"] for link in links}

	children = []
	if own_ids:
		children = frappe.get_all(
			"iCorp Client Link",
			filters={"parent_client": ["in", list(own_ids)]},
			fields=["name", "display_label", "is_active", "parent_client", "customer"],
			order_by="is_active desc, client_name asc",
		)

	children_by_parent: dict[str, list[dict]] = {}
	for child in children:
		children_by_parent.setdefault(child["parent_client"], []).append(child)

	for link in links:
		parent = link.get("parent_client")
		if parent and parent in own_ids:
			relationship = f"Location of {label_by_id.get(parent, parent)}"
		elif parent:
			parent_customer = frappe.db.get_value("iCorp Client Link", parent, "customer")
			parent_label = frappe.db.get_value("iCorp Client Link", parent, "display_label")
			if parent_customer:
				relationship = f"Managed by {parent_customer}"
			else:
				relationship = f"Parent unassigned ({parent_label})"
		else:
			kids = children_by_parent.get(link["name"], [])
			own = sum(1 for k in kids if k["customer"] == doc.name)
			other = sum(1 for k in kids if k["customer"] and k["customer"] != doc.name)
			unassigned = sum(1 for k in kids if not k["customer"])
			parts = []
			if own:
				parts.append(f"Master of {_plural(own, 'location')}")
			if other:
				parts.append(f"Partner: manages {_plural(other, 'client')} for other Customers")
			if unassigned:
				parts.append(f"{_plural(unassigned, 'child client')} unassigned")
			relationship = "; ".join(parts) or "Standalone"

		if link.get("is_partner_client"):
			relationship += " (flagged partner in iCorp)"
		link["relationship"] = relationship
		link["partner_customer"] = derive_partner(link["name"])
		link["partner_icorp_client_id"] = derive_partner_client(link["name"])

	managed = [
		{
			"name": child["name"],
			"display_label": child["display_label"],
			"is_active": child["is_active"],
			"customer": child["customer"] or "",
			"via": label_by_id.get(child["parent_client"], child["parent_client"]),
		}
		for child in children
		if child["customer"] != doc.name
	]

	doc.set_onload("icorp_clients", links)
	doc.set_onload("icorp_managed_clients", managed)
