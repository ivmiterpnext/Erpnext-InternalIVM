"""
Delete orphaned Property Setters, dead Custom Fields, and mis-tagged
customization records across multiple doctypes.

Root cause: ivm.patches.populate_ivm_module_on_customizations blanket-tagged
every Property Setter and unattributed Custom Field on the site as
module="IVM", regardless of actual ownership. This caused
bench export-customizations to export records belonging to ERPNext Regional,
HRMS, CRM, and Frappe core into IVM's custom/ directory. Additionally,
several Custom Fields carried over from the v14->v16 migration are confirmed
dead (no data, no code references, no DB columns).

This patch:
1. Deletes Property Setters that are either redundant with ERPNext defaults
   or were developer-created noise from Customize Form sessions (rounding
   fields, print visibility, barcode hidden=0, naming series options that
   match defaults, default print formats, stale field_order overrides).
2. Deletes dead Custom Fields (ghost fields with no column, no data, or no
   code consumers).
3. Clears module="IVM" back to NULL on Custom Fields and Property Setters
   that belong to other apps (ERPNext Regional, HRMS, CRM, Frappe core)
   so they stop appearing in IVM's export-customizations output.
4. Drops orphaned DB columns for confirmed-dead Custom Fields.

Each record was individually reviewed before inclusion. See the grouping
comments below for per-doctype rationale.

Safe to run repeatedly (idempotent).
"""

import frappe

# --- Property Setters to DELETE ---
# Grouped by doctype. All are either redundant with ERPNext/Frappe defaults
# or were developer-created noise from Customize Form sessions.

PROPERTY_SETTERS_TO_DELETE = [
	# Task Type
	"Task Type-main-allow_import",
	# Task -- stale field_order (same class of bug as WR's)
	"Task-main-field_order",
	# Supplier -- naming series overrides (hiding field, removing required,
	# options matching default)
	"Supplier-naming_series-hidden",
	"Supplier-naming_series-reqd",
	"Supplier-naming_series-options",
	# Supplier Quotation -- rounding/print noise
	"Supplier Quotation-base_rounded_total-hidden",
	"Supplier Quotation-base_rounded_total-print_hide",
	"Supplier Quotation-disable_rounded_total-default",
	"Supplier Quotation-in_words-hidden",
	"Supplier Quotation-in_words-print_hide",
	"Supplier Quotation-rounded_total-hidden",
	"Supplier Quotation-rounded_total-print_hide",
	# Sales Order -- rounding/print noise + default print format + redundant
	"Sales Order-base_rounded_total-hidden",
	"Sales Order-base_rounded_total-print_hide",
	"Sales Order-disable_rounded_total-default",
	"Sales Order-due_date-print_hide",
	"Sales Order-in_words-hidden",
	"Sales Order-in_words-print_hide",
	"Sales Order-main-default_print_format",
	"Sales Order-naming_series-options",
	"Sales Order-payment_schedule-print_hide",
	"Sales Order-rounded_total-hidden",
	"Sales Order-rounded_total-print_hide",
	"Sales Order-scan_barcode-hidden",
	"Sales Order-tax_id-hidden",
	"Sales Order-tax_id-print_hide",
	"Sales Order-utm_analytics_section-hidden",
	# Sales Invoice -- rounding/print noise + default print format +
	# discount account hiding + redundant
	"Sales Invoice-additional_discount_account-hidden",
	"Sales Invoice-additional_discount_account-mandatory_depends_on",
	"Sales Invoice-base_rounded_total-hidden",
	"Sales Invoice-base_rounded_total-print_hide",
	"Sales Invoice-commission_section-hidden",
	"Sales Invoice-disable_rounded_total-default",
	"Sales Invoice-due_date-print_hide",
	"Sales Invoice-in_words-hidden",
	"Sales Invoice-in_words-print_hide",
	"Sales Invoice-main-default_print_format",
	"Sales Invoice-naming_series-options",
	"Sales Invoice-payment_schedule-print_hide",
	"Sales Invoice-rounded_total-hidden",
	"Sales Invoice-rounded_total-print_hide",
	"Sales Invoice-sales_team_section-hidden",
	"Sales Invoice-scan_barcode-hidden",
	"Sales Invoice-tax_id-hidden",
	"Sales Invoice-tax_id-print_hide",
	"Sales Invoice-utm_analytics_section-hidden",
	# Sales Invoice Item
	"Sales Invoice Item-barcode-hidden",
	"Sales Invoice Item-discount_account-hidden",
	"Sales Invoice Item-discount_account-mandatory_depends_on",
	"Sales Invoice Item-target_warehouse-hidden",
	# Quotation -- rounding/print noise + default print format
	"Quotation-base_rounded_total-hidden",
	"Quotation-base_rounded_total-print_hide",
	"Quotation-disable_rounded_total-default",
	"Quotation-in_words-hidden",
	"Quotation-in_words-print_hide",
	"Quotation-main-default_print_format",
	"Quotation-rounded_total-hidden",
	"Quotation-rounded_total-print_hide",
	"Quotation-scan_barcode-hidden",
	"Quotation-utm_analytics_section-hidden",
	# Request for Quotation
	"Request for Quotation-main-default_print_format",
	# Purchase Receipt -- rounding/print noise + redundant
	"Purchase Receipt-base_rounded_total-hidden",
	"Purchase Receipt-base_rounded_total-print_hide",
	"Purchase Receipt-disable_rounded_total-default",
	"Purchase Receipt-in_words-hidden",
	"Purchase Receipt-in_words-print_hide",
	"Purchase Receipt-provisional_expense_account-hidden",
	"Purchase Receipt-rounded_total-hidden",
	"Purchase Receipt-rounded_total-print_hide",
	"Purchase Receipt-scan_barcode-hidden",
	# Purchase Receipt Item
	"Purchase Receipt Item-barcode-hidden",
	"Purchase Receipt Item-from_warehouse-hidden",
	# Purchase Order -- rounding/print noise + default print format
	"Purchase Order-base_rounded_total-hidden",
	"Purchase Order-base_rounded_total-print_hide",
	"Purchase Order-disable_rounded_total-default",
	"Purchase Order-due_date-print_hide",
	"Purchase Order-in_words-hidden",
	"Purchase Order-in_words-print_hide",
	"Purchase Order-main-default_print_format",
	"Purchase Order-naming_series-options",
	"Purchase Order-payment_schedule-print_hide",
	"Purchase Order-rounded_total-hidden",
	"Purchase Order-rounded_total-print_hide",
	"Purchase Order-scan_barcode-hidden",
	# Purchase Invoice -- rounding/print noise + default print format
	"Purchase Invoice-base_rounded_total-hidden",
	"Purchase Invoice-base_rounded_total-print_hide",
	"Purchase Invoice-disable_rounded_total-default",
	"Purchase Invoice-due_date-print_hide",
	"Purchase Invoice-in_words-hidden",
	"Purchase Invoice-in_words-print_hide",
	"Purchase Invoice-main-default_print_format",
	"Purchase Invoice-payment_schedule-print_hide",
	"Purchase Invoice-rounded_total-hidden",
	"Purchase Invoice-rounded_total-print_hide",
	"Purchase Invoice-scan_barcode-hidden",
	# Purchase Invoice Item
	"Purchase Invoice Item-from_warehouse-hidden",
]

# --- Custom Fields to DELETE ---
# Dead fields: no column, no data, or no code consumer.

CUSTOM_FIELDS_TO_DELETE = [
	# User -- v14 migration ghosts, renamed with _pin suffix, columns never
	# created, no data on dev or prod
	"company_name_pin",
	"department_pin",
	"extension_pin",
	"fax_pin",
	"manager_pin",
	"title_pin",
	# User Group -- duplicates built-in Frappe system field
	"User Group-owner",
	# ToDo -- zero data across 129k records, zero code references
	"ToDo-task_id",
	# Sales Stage -- populated but zero code consumers, confirmed dead
	"Sales Stage-percentage",
]

# --- Custom Fields with columns to DROP after deleting the CF record ---
COLUMNS_TO_DROP = [
	("tabToDo", "task_id"),
	("tabSales Stage", "percentage"),
]

# --- Property Setters to UNTAG (clear module back to NULL) ---
# Frappe auto-generated, not IVM's. Clearing module prevents them from
# appearing in future export-customizations runs.

PROPERTY_SETTERS_TO_UNTAG = [
	"Version-data-in_list_view",
	"Version-docname-in_list_view",
	"Version-ref_doctype-in_list_view",
	"Stock Reconciliation-scan_barcode-hidden",
	"Stock Reconciliation Item-barcode-hidden",
	"Stock Entry-naming_series-options",
	"Stock Entry-scan_barcode-hidden",
	"Stock Entry Detail-barcode-hidden",
]

# --- Custom Fields to UNTAG (clear module back to NULL) ---
# Belong to ERPNext Regional, HRMS, or CRM -- not IVM's.

CUSTOM_FIELDS_TO_UNTAG = [
	"UTM Campaign-crm_campaign",
	"Task-total_expense_claim",
	"Terms and Conditions-hr",
	"Supplier-irs_1099",
	"Sales Order-exempt_from_sales_tax",
	"Sales Invoice-exempt_from_sales_tax",
	"Quotation-exempt_from_sales_tax",
]


def execute():
	# 1. Delete Property Setters
	for name in PROPERTY_SETTERS_TO_DELETE:
		if frappe.db.exists("Property Setter", name):
			frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)
			print(f"  Deleted Property Setter: {name}")
		else:
			print(f"  Property Setter {name} does not exist -- skipping")

	# 2. Delete Custom Fields
	for name in CUSTOM_FIELDS_TO_DELETE:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)
			print(f"  Deleted Custom Field: {name}")
		else:
			print(f"  Custom Field {name} does not exist -- skipping")

	# 3. Untag Property Setters (clear module)
	for name in PROPERTY_SETTERS_TO_UNTAG:
		if frappe.db.exists("Property Setter", name):
			frappe.db.set_value("Property Setter", name, "module", None, update_modified=False)
			print(f"  Cleared module on Property Setter: {name}")
		else:
			print(f"  Property Setter {name} does not exist -- skipping")

	# 4. Untag Custom Fields (clear module)
	for name in CUSTOM_FIELDS_TO_UNTAG:
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "module", None, update_modified=False)
			print(f"  Cleared module on Custom Field: {name}")
		else:
			print(f"  Custom Field {name} does not exist -- skipping")

	# 5. Drop orphaned columns (must commit first to avoid ImplicitCommitError)
	frappe.db.commit()

	for table, column in COLUMNS_TO_DROP:
		existing = {row[0] for row in frappe.db.sql(f"SHOW COLUMNS FROM `{table}`")}
		if column in existing:
			frappe.db.sql_ddl(f"ALTER TABLE `{table}` DROP COLUMN `{column}`")
			print(f"  Dropped column {table}.{column}")
		else:
			print(f"  {table}.{column} does not exist -- skipping")

	# 6. Clear caches for affected doctypes
	for dt in [
		"Task Type",
		"Task",
		"Supplier",
		"Supplier Quotation",
		"Sales Order",
		"Sales Invoice",
		"Sales Invoice Item",
		"Quotation",
		"Request for Quotation",
		"Purchase Receipt",
		"Purchase Receipt Item",
		"Purchase Order",
		"Purchase Invoice",
		"Purchase Invoice Item",
		"Version",
		"Stock Reconciliation",
		"Stock Reconciliation Item",
		"Stock Entry",
		"Stock Entry Detail",
		"UTM Campaign",
		"Terms and Conditions",
		"User",
		"User Group",
		"ToDo",
		"Sales Stage",
	]:
		frappe.clear_cache(doctype=dt)
