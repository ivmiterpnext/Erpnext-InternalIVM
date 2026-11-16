"""
Drop Project.custom_master_customer, superseded by the derived Project.partner_customer
field (set from the iCorp client's parent_client Customer, see
ivm.deployments.services.deployment_clients.derive_partner).

Before dropping the column, copies any non-blank custom_master_customer into partner_customer
for Projects where partner_customer is blank (only when the target Customer exists). This makes
the patch self-contained: it no longer depends on ivm.deployments.patches.backfill_project_icorp_client
having run first.

Frappe does not drop columns automatically on migrate, so this patch removes both
the orphaned Custom Field record and the leftover DB column. Safe to run even if
either is already gone.

NOT registered in deploy 1 (partner_customer doesn't exist at patch time on prod; it's created by sync_customizations after patches). Register in the teardown deploy, once partner_customer exists.
"""

import frappe


def execute():
	table = "tabProject"
	column = "custom_master_customer"

	existing_columns = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}

	if column in existing_columns:
		_copy_to_partner_customer()

	custom_field_name = "Project-custom_master_customer"
	if frappe.db.exists("Custom Field", custom_field_name):
		frappe.delete_doc("Custom Field", custom_field_name, ignore_permissions=True)

	if column not in existing_columns:
		print(f"{table}.{column} does not exist — nothing to do.")
		return

	frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
	print(f"Dropped column {table}.{column}.")


def _copy_to_partner_customer():
	where = """
		FROM `tabProject` p
		INNER JOIN `tabCustomer` c ON c.name = p.custom_master_customer
		WHERE (p.partner_customer IS NULL OR p.partner_customer = '')
		  AND p.custom_master_customer IS NOT NULL
		  AND p.custom_master_customer != ''
		  AND p.custom_master_customer != COALESCE(p.customer, '')
	"""
	count = frappe.db.sql(f"SELECT COUNT(*) {where}")[0][0]
	if count:
		frappe.db.sql(
			"UPDATE `tabProject` p INNER JOIN `tabCustomer` c ON c.name = p.custom_master_customer SET p.partner_customer = p.custom_master_customer WHERE (p.partner_customer IS NULL OR p.partner_customer = '') AND p.custom_master_customer IS NOT NULL AND p.custom_master_customer != '' AND p.custom_master_customer != COALESCE(p.customer, '')"
		)
	print(f"Copied custom_master_customer to partner_customer on {count} Project(s).")
