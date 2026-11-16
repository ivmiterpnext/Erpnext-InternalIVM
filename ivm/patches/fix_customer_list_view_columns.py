"""
Establish the correct Customer list view columns: Name (always shown) + Customer Name +
iCorp Client ID + Account Owner. Everything else (Account Site, Customer Group, Customer
Type, Billing Currency, Territory) hidden from the list view.

Supersedes an earlier, incomplete attempt (drop_customer_in_list_view_property_setters,
removed) that only deleted the 8 original in_list_view Property Setters. That was
insufficient on its own because several of these fields have `in_list_view=1` baked in at a
layer *below* the Property Setter:

- `account_owner` / `account_site` are ivm Custom Fields with `in_list_view=1` set directly
  on the Custom Field's own definition (not just a Property Setter override).
- `customer_type` / `default_currency` (label "Billing Currency") default to `in_list_view=1`
  natively in ERPNext core's own Customer doctype schema.

Simply deleting the old Property Setters left those four still visible (the override was
redundant or simply absent, so the underlying default of 1 won), and caused a regression on
`customer_group` / `territory`, which previously had an explicit override forcing them off —
removing that override reverted them to ERPNext core's default of 1 as well.

This patch fixes it at the correct layer for each field:
- Custom Fields (account_owner, account_site, icorp_client_id): their own `in_list_view`
  attribute is set directly (0 for the two Account fields; icorp_client_id's own attribute is
  already 0 in the Custom Field's native definition and is left alone).
- Core ERPNext fields (customer_group, customer_type, default_currency, territory): an
  explicit Property Setter forcing `in_list_view=0` is created/updated, overriding core's
  native default of 1.
- The three fields that should show (account_owner, customer_name, icorp_client_id) get an
  explicit Property Setter forcing `in_list_view=1`, so they display regardless of any
  future change to their underlying default.

Safe to run repeatedly (idempotent).
"""

import frappe

CUSTOM_FIELD_OVERRIDES = {
	"account_owner": 0,
	"account_site": 0,
}

PROPERTY_SETTER_VALUES = {
	"account_owner": "1",
	"customer_name": "1",
	"icorp_client_id": "1",
	"account_site": "0",
	"customer_group": "0",
	"customer_type": "0",
	"default_currency": "0",
	"territory": "0",
}


def execute():
	for fieldname, value in CUSTOM_FIELD_OVERRIDES.items():
		cf_name = f"Customer-{fieldname}"
		if frappe.db.exists("Custom Field", cf_name):
			frappe.db.set_value("Custom Field", cf_name, "in_list_view", value)
			print(f"  Set Custom Field {cf_name}.in_list_view = {value}")

	for field_name, value in PROPERTY_SETTER_VALUES.items():
		name = f"Customer-{field_name}-in_list_view"
		if frappe.db.exists("Property Setter", name):
			frappe.db.set_value("Property Setter", name, "value", value)
			print(f"  Updated Property Setter: {name} = {value}")
		else:
			doc = frappe.get_doc(
				{
					"doctype": "Property Setter",
					"doc_type": "Customer",
					"doctype_or_field": "DocField",
					"field_name": field_name,
					"property": "in_list_view",
					"property_type": "Check",
					"value": value,
					"module": "IVM",
				}
			)
			doc.insert(ignore_permissions=True)
			print(f"  Created Property Setter: {name} = {value}")

	frappe.db.commit()
	frappe.clear_cache(doctype="Customer")
