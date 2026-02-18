"""
Migration patch to set deployment_structure_version on existing Project records.
- Version 1: Legacy deployments (created before cutoff date)
- Version 2: Current structure (created after cutoff date)
"""

import frappe
from ivm.utils.deployment_versions import (
	get_deployment_version_for_date,
	get_deployment_cutoff_date,
	VERSION_1_LEGACY,
	VERSION_2_CURRENT
)


def execute():
	"""
	Set deployment_structure_version on existing Project records based on creation date.
	"""
	try:
		cutoff_date = get_deployment_cutoff_date()
		
		frappe.logger().info(f"Setting deployment structure versions for projects (cutoff: {cutoff_date})")
		
		# Get all projects
		projects = frappe.get_all(
			"Project",
			fields=["name", "creation"],
			filters={}
		)
		
		v1_count = 0  # Legacy
		v2_count = 0  # Current
		
		for project in projects:
			# Use utility function to determine version
			version = get_deployment_version_for_date(project.creation)
			
			# Update the version
			frappe.db.set_value(
				"Project",
				project.name,
				"deployment_structure_version",
				version,
				update_modified=False  # Don't update modified timestamp
			)
			
			if version == VERSION_1_LEGACY:
				v1_count += 1
			elif version == VERSION_2_CURRENT:
				v2_count += 1
		
		frappe.db.commit()
		
		frappe.logger().info(
			f"Deployment versions set: {v1_count} legacy (v1), {v2_count} current (v2)"
		)
		
		print(f"✓ Set deployment structure versions: {v1_count} v1 (legacy), {v2_count} v2 (current)")
		
	except Exception as e:
		frappe.logger().error(f"Error setting deployment structure versions: {str(e)}")
		raise
