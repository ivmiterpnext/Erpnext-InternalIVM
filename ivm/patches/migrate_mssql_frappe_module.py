"""
Migration patch to handle transition of MSSQL Frappe module from mssql_frappe app to ivm app.

This patch ensures all DocTypes and data remain accessible after merging mssql_frappe
as a module within the ivm app.
"""

import frappe


def execute():
	"""
	Migrate MSSQL Frappe module from mssql_frappe app to ivm app.
	
	Frappe's module system should automatically detect the module's new location,
	but this patch ensures the transition is smooth and logs the process.
	"""
	frappe.logger().info("Starting migration of MSSQL Frappe module from mssql_frappe app to ivm app")
	
	try:
		# Get all DocTypes from MSSQL Frappe module
		doctypes = frappe.get_all(
			"DocType",
			filters={"module": "MSSQL Frappe"},
			fields=["name", "module"]
		)
		
		frappe.logger().info(f"Found {len(doctypes)} DocTypes in MSSQL Frappe module")
		
		# Frappe's module map will be rebuilt on next startup
		# We just need to clear any cached module paths
		frappe.clear_cache()
		
		# Verify a few key DocTypes are still accessible
		sample_doctypes = ["Address Link", "Client Link", "Board Link", "Machine Link"]
		accessible_count = 0
		
		for dt in sample_doctypes:
			if frappe.db.exists("DocType", dt):
				try:
					# Try to get the DocType controller
					frappe.get_doc("DocType", dt)
					accessible_count += 1
					frappe.logger().info(f"✓ DocType '{dt}' is accessible")
				except Exception as e:
					frappe.logger().warning(f"✗ DocType '{dt}' not accessible: {str(e)}")
		
		frappe.logger().info(f"Migration complete. {accessible_count}/{len(sample_doctypes)} sample DocTypes verified")
		
		if accessible_count < len(sample_doctypes):
			frappe.logger().warning("Some DocTypes may need attention. Check logs for details.")
		
	except Exception as e:
		frappe.logger().error(f"Error during migration: {str(e)}")
		raise
