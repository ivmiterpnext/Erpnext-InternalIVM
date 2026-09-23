"""
Remove dead Client Scripts that reference non-existent fields/child-tables.

These Client Scripts were referencing fields and child-tables that no longer exist
on their target doctypes:
- "Test Button 3 Opp" and "Test Override": referenced Opportunity's
  deployment_locations child-table and opportunity field (both removed)
- "Create Deployment Location From Opportunity": referenced Opportunity's
  deployment_locations child-table (removed)
- "Warehouse Request Created By" and "Warehouse Request Naming": referenced
  Warehouse Request's created_by, created_date, and warehouse_request_name
  fields (all dropped in prior patches)
- "Close Button": was fully overwriting ERPNext core's default Issue list view
  behavior (status=Open filter, colwidths, priority-based indicator) via a plain
  frappe.listview_settings["Issue"] = {...} reassignment. This is being consolidated
  back onto ERPNext core's own issue_list.js per Frappe's __list_js/__custom_list_js
  load order in frappe/desk/form/meta.py + frappe/public/js/frappe/model/model.js::init_doctype.
"""

import frappe


def execute():
	scripts_to_delete = [
		"Test Button 3 Opp",
		"Test Override",
		"Create Deployment Location From Opportunity",
		"Warehouse Request Created By",
		"Warehouse Request Naming",
		"Close Button",
	]

	for script_name in scripts_to_delete:
		if frappe.db.exists("Client Script", script_name):
			frappe.delete_doc("Client Script", script_name, ignore_permissions=True)
			print(f"  Deleted Client Script '{script_name}'")
		else:
			print(f"  Client Script '{script_name}' not found — skipping")
