"""iCorp client list sync: upserts identity fields (name, active, parent) for every iCorp client
into iCorp Client Link. Runs daily (scheduler_events in hooks.py). Never touches a Link's customer
assignment, which is a Frappe-side decision.
"""

import frappe

from ivm.integrations.icorp.api import icorp_api_get
from ivm.integrations.keyvault import get_config_value


def _icorp_is_configured() -> bool:
	"""True if this site has iCorp API credentials configured at all (site_config or
	environment variable). Used to let apply_on_migrate skip cleanly, rather than
	fail the migrate, on a site that was never set up to run this -- e.g. test.local,
	which shares ivm's codebase with dev.local but has no iCorp credentials of its
	own and isn't meant to run the consolidation."""
	return bool(get_config_value("AZURE_KEYVAULT_URL")) and bool(get_config_value("ICORP_API_BASE_URL"))


def fetch_icorp_clients() -> list[dict]:
	"""GET Client?page=1&pageSize=5000 via icorp_api_get, return response["data"]."""
	response = icorp_api_get("Client?page=1&pageSize=5000")
	return response.get("data", [])


def sync_icorp_client_links() -> dict:
	"""Upsert identity fields (name, active, parent) for every iCorp client. Never touches
	customer / assignment_source / proposed_customer / match_status / match_evidence — those are
	Frappe-side decisions, not iCorp data."""
	if not _icorp_is_configured():
		frappe.logger("icorp_client_sync").info(
			"sync_icorp_client_links skipped: iCorp API credentials are not configured on this site."
		)
		return

	clients = fetch_icorp_clients()
	created, updated = 0, 0

	for client in clients:
		client_id = str(client["id"])
		display_label = f"({client_id}) {client.get('name') or ''}".strip()
		values = {
			"client_name": client.get("name") or "",
			"display_label": display_label,
			"is_active": 1 if client.get("is_active") else 0,
			"is_partner_client": 1 if client.get("is_partner_client") else 0,
			"sv_location_count_active": client.get("sv_location_count_active") or 0,
			"sv_machine_count_active": client.get("sv_machine_count_active") or 0,
		}

		if frappe.db.exists("iCorp Client Link", client_id):
			frappe.db.set_value("iCorp Client Link", client_id, values)
			updated += 1
		else:
			doc = frappe.get_doc({"doctype": "iCorp Client Link", "icorp_client_id": client_id, **values})
			doc.insert(ignore_permissions=True)
			created += 1

	# second pass: parent links, once every client row exists
	for client in clients:
		parent_id = client.get("partner_client_id")
		client_id = str(client["id"])
		parent_value = str(parent_id) if parent_id else ""
		if parent_value and not frappe.db.exists("iCorp Client Link", parent_value):
			parent_value = ""  # defensive: shouldn't happen, but don't link to a non-existent row
		frappe.db.set_value("iCorp Client Link", client_id, "parent_client", parent_value)

	frappe.db.commit()
	return {"total": len(clients), "created": created, "updated": updated}
