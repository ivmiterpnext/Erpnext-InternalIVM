"""Drop the legacy Customer.icorp_client_id field and its DB column, superseded by
Customer.icorp_client_ids (see backfill_customer_icorp_client_ids.py) and the HubSpot
resolver rewire in backfill_deals_from_hubspot.py / deal_handler.py. Safe to re-run —
every step is existence-guarded."""

import frappe


def execute():
	if frappe.db.exists("Property Setter", "Customer-icorp_client_id-in_list_view"):
		frappe.delete_doc("Property Setter", "Customer-icorp_client_id-in_list_view", ignore_permissions=True)

	if frappe.db.exists("Custom Field", "Customer-icorp_client_id"):
		frappe.delete_doc("Custom Field", "Customer-icorp_client_id", ignore_permissions=True)

	if frappe.db.has_column("Customer", "icorp_client_id"):
		frappe.db.sql_ddl("ALTER TABLE `tabCustomer` DROP COLUMN `icorp_client_id`")

	frappe.clear_cache(doctype="Customer")
