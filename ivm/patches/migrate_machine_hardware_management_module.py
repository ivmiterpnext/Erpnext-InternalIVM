"""
Migration patch to handle transition of Machine Hardware Management module from machine_hardware_management app to ivm app.

This patch ensures all DocTypes and data remain accessible after merging machine_hardware_management
as a module within the ivm app.
"""

import frappe


def execute():
	"""
	Migrate Machine Hardware Management module from machine_hardware_management app to ivm app.
	
	Frappe's module system should automatically detect the module's new location,
	but this patch ensures the transition is smooth and logs the process.
	"""
	frappe.logger().info("Starting migration of Machine Hardware Management module from machine_hardware_management app to ivm app")
	
	try:
		# Get all DocTypes from Machine Hardware Management module
		doctypes = frappe.get_all(
			"DocType",
			filters={"module": "Machine Hardware Management"},
			fields=["name", "module"]
		)
		
		frappe.logger().info(f"Found {len(doctypes)} DocTypes in Machine Hardware Management module")
		
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
