"""
Drop three Customer Custom Fields/columns that are no longer used:
- account_number (confirmed unused anywhere in this app's codebase)
- partner_icorp_client (a stray field from early exploration, never wired to any code)
- custom_master_customer ("Master Client" -- superseded by the derived Partner shown
  on the Customer form's iCorp tab; its one live write site, in
  provision_client_from_deal.py, has been removed)

Frappe does not drop columns automatically on migrate, and fixture/customization sync
never deletes a Custom Field that's simply absent from the JSON -- so removing a field
from ivm/ivm/custom/customer.json alone only stops it being recreated/updated; it does
not touch the live Custom Field record or the physical column already sitting in any
site's database. This patch does both explicitly, for every one of the three fields.

Safe to re-run: each field/column is only touched if it still exists. dev.local already
had account_number and partner_icorp_client removed by hand earlier, and
custom_master_customer removed the same way in the same piece of work that added this
patch -- so on dev.local this patch is a fast no-op. On every other site (prod, any
future fresh site), this is what actually removes all three.
"""

import csv

import frappe

_FIELDS_TO_DROP = ["account_number", "partner_icorp_client", "custom_master_customer"]


def execute():
	for fieldname in _FIELDS_TO_DROP:
		if frappe.db.has_column("Customer", fieldname):
			_backup_nonempty_values(fieldname)

		custom_field_name = f"Customer-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, ignore_permissions=True)

		if frappe.db.has_column("Customer", fieldname):
			frappe.db.sql_ddl(f"ALTER TABLE `tabCustomer` DROP COLUMN `{fieldname}`")


def _backup_nonempty_values(fieldname):
	rows = frappe.db.sql(
		f"SELECT `name`, `{fieldname}` FROM `tabCustomer` WHERE `{fieldname}` IS NOT NULL AND `{fieldname}` != ''"
	)
	if not rows:
		return

	backup_path = frappe.get_site_path(
		"private", "files", f"customer_{fieldname}_backup_{frappe.utils.nowdate()}.csv"
	)
	with open(backup_path, "w", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(["name", fieldname])
		writer.writerows(rows)

	print(f"Backed up {len(rows)} non-empty Customer.{fieldname} value(s) to {backup_path}")
