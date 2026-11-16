"""
Backfill Project.icorp_client_id and Project.partner_customer from the legacy
Project.client_id free-text field, ahead of dropping Project.custom_master_customer.

Report-only for customer mismatches -- this patch never changes Project.customer.
Safe to re-run: it skips Projects where icorp_client_id is already set.
"""

import csv
import os

import frappe

from ivm.deployments.services.deployment_clients import derive_partner, parse_project_client_ids


def execute():
	run_backfill()


def _valid_partner(candidate, project_customer):
	"""Return candidate as a partner_customer, or None if blank or equal to the Project's own customer."""
	if not candidate or candidate == project_customer:
		return None
	return candidate


def run_backfill():
	has_master_col = frappe.db.has_column("Project", "custom_master_customer")
	fields = ["name", "customer", "client_id"]
	if has_master_col:
		fields.append("custom_master_customer")

	rows = frappe.get_all(
		"Project",
		filters={
			"project_type": "Deployment",
			"client_id": ["is", "set"],
			"icorp_client_id": ["is", "not set"],
		},
		fields=fields,
	)

	report = []
	for row in rows:
		parsed = parse_project_client_ids(row.client_id)
		status = "unresolved_id"
		resolved_client = None
		client_customer = None
		partner = None

		if parsed["primary"] and frappe.db.exists("iCorp Client Link", parsed["primary"]):
			resolved_client = parsed["primary"]
			status = "multi_id" if parsed["others"] else "linked"
			client_customer = frappe.db.get_value("iCorp Client Link", resolved_client, "customer")
			if client_customer and row.customer and client_customer != row.customer:
				status = "customer_mismatch"

			partner = _valid_partner(derive_partner(resolved_client), row.customer)
			if not partner and has_master_col:
				partner = _valid_partner(row.get("custom_master_customer"), row.customer)
			if not partner and parsed["master"] and frappe.db.exists("iCorp Client Link", parsed["master"]):
				partner = _valid_partner(
					frappe.db.get_value("iCorp Client Link", parsed["master"], "customer"), row.customer
				)

			update_values = {"icorp_client_id": resolved_client}
			if partner:
				update_values["partner_customer"] = partner
			frappe.db.set_value("Project", row.name, update_values, update_modified=False)

		report.append(
			{
				"project": row.name,
				"customer": row.customer,
				"client_id": row.client_id,
				"resolved_client": resolved_client,
				"client_customer": client_customer,
				"partner": partner,
				"status": status,
			}
		)

	if report:
		site_path = frappe.get_site_path("private", "files")
		os.makedirs(site_path, exist_ok=True)
		filename = f"project_client_backfill_{frappe.utils.nowdate()}.csv"
		path = os.path.join(site_path, filename)
		with open(path, "w", newline="") as f:
			writer = csv.DictWriter(
				f,
				fieldnames=[
					"project",
					"customer",
					"client_id",
					"resolved_client",
					"client_customer",
					"partner",
					"status",
				],
			)
			writer.writeheader()
			writer.writerows(report)
		frappe.logger("deployments").info(f"Project client backfill report: {path} ({len(report)} rows)")
