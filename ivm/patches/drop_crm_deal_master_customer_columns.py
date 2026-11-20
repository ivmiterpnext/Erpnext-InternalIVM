"""
Drop the CRM Deal master-client fields (customer consolidation teardown):
- CRM Deal.custom_master_customer
- CRM Deal.custom_master_organization
- CRM Deal.custom_master_client_id

The Custom Field definitions were removed from ivm/ivm/custom/crm_deal.json. Frappe does not
drop columns or Custom Field records automatically, and sync_customizations() re-creates any
Custom Field record that still exists in the database, so this patch deletes the Custom Field
records and then drops the columns.

custom_master_client_id was already dropped once by ivm.patches.drop_customer_and_crm_deal_master_client_columns,
but its Custom Field record survived and the column was re-created on the next migrate. This patch
removes both.

Refuses to drop custom_master_customer / custom_master_organization while either still holds
data, so no values are lost silently.

Safe to run repeatedly; every step checks existence first.
"""

import frappe

TABLE = "tabCRM Deal"
FIELDS = ["custom_master_customer", "custom_master_organization", "custom_master_client_id"]
MUST_BE_EMPTY = ["custom_master_customer", "custom_master_organization"]


def execute():
	populated = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `{TABLE}`
		WHERE {" OR ".join(f"(`{f}` IS NOT NULL AND `{f}` != '')" for f in MUST_BE_EMPTY)}
		"""
	)[0][0]
	if populated:
		frappe.throw(
			f"Refusing to drop CRM Deal master-client columns: {populated} deal(s) still hold a value "
			f"in {', '.join(MUST_BE_EMPTY)}. Clear or migrate them, then re-run migrate."
		)

	for fieldname in FIELDS:
		custom_field_name = f"CRM Deal-{fieldname}"
		if frappe.db.exists("Custom Field", custom_field_name):
			frappe.delete_doc("Custom Field", custom_field_name, ignore_permissions=True, force=True)

	# Commit pending deletes before DDL (ImplicitCommitError otherwise — see CLAUDE.md).
	frappe.db.commit()

	existing_columns = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{TABLE}`")}
	for fieldname in FIELDS:
		if fieldname in existing_columns:
			frappe.db.sql_ddl(f"ALTER TABLE `{TABLE}` DROP COLUMN `{fieldname}`")
