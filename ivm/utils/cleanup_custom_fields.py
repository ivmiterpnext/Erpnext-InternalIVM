"""Cleanup deleted custom fields from JSON files"""
import json
import os
import frappe
from frappe import scrub


def cleanup_deleted_fields(doctype, silent=False, exclude_field=None, exclude_fields=None):
	"""Remove custom fields from JSON that no longer exist in database
	
	Args:
		doctype: The DocType to clean up
		silent: If True, suppress print output (for auto-export). If False, show detailed output.
		exclude_field: Single field name to explicitly remove (deprecated, use exclude_fields)
		exclude_fields: List of field names to explicitly remove (used when on_trash fires before DB deletion)
	"""
	
	def log(msg):
		"""Print only if not silent"""
		if not silent:
			print(msg)
	
	# Normalize exclude fields to a set
	fields_to_exclude = set()
	if exclude_fields:
		fields_to_exclude = set(exclude_fields) if isinstance(exclude_fields, list) else {exclude_fields}
	elif exclude_field:
		fields_to_exclude = {exclude_field}
	
	# Get the path to the custom file
	module_name = "ivm"
	file_path = frappe.get_app_path("ivm", module_name, "custom", f"{scrub(doctype)}.json")
	
	if not os.path.exists(file_path):
		log(f"No custom file found for {doctype}")
		return
	
	# Read the existing JSON
	with open(file_path, "r") as f:
		data = json.load(f)
	
	if "custom_fields" not in data:
		log(f"No custom_fields found in {doctype} JSON")
		return
	
	# Get all current custom fields from database
	db_fields = frappe.get_all(
		"Custom Field",
		filters={"dt": doctype},
		pluck="name"
	)
	
	db_field_set = set(db_fields)
	
	# Remove excluded fields from the DB set (treat them as already deleted)
	if fields_to_exclude:
		db_field_set -= fields_to_exclude
		log(f"Explicitly excluding {len(fields_to_exclude)} field(s) being deleted: {', '.join(fields_to_exclude)}")
	
	# Find fields in JSON that don't exist in database
	json_fields = data["custom_fields"]
	fields_to_remove = []
	
	for field in json_fields:
		field_name = field.get("name")
		if field_name and field_name not in db_field_set:
			fields_to_remove.append(field_name)
	
	# Remove the deleted fields from custom_fields if any found
	if fields_to_remove:
		# Show what will be removed
		log(f"\n🗑️  Found {len(fields_to_remove)} deleted field(s) in {doctype} JSON:")
		for field_name in fields_to_remove:
			log(f"  - {field_name}")
		
		# Remove the deleted fields
		data["custom_fields"] = [
			field for field in json_fields
			if field.get("name") not in fields_to_remove
		]
	else:
		log(f"✅ No deleted fields found in {doctype} custom_fields")

	
	# Do the same for property_setters if they exist
	if "property_setters" in data:
		# Get ALL custom field fieldnames from the database (not just from JSON)
		# This helps us identify which fields in field_order are custom vs standard
		# even after export_customizations has already cleaned the JSON
		db_custom_field_fieldnames = frappe.get_all(
			"Custom Field",
			filters={"dt": doctype},
			pluck="fieldname"
		)
		# Also include any fields we're explicitly excluding (being deleted in this request)
		all_custom_field_names = set(db_custom_field_fieldnames)
		if fields_to_exclude:
			# Get fieldnames from the JSON for the excluded fields
			excluded_fieldnames = {
				field.get("fieldname") for field in json_fields 
				if field.get("name") in fields_to_exclude and field.get("fieldname")
			}
			all_custom_field_names.update(excluded_fieldnames)
		
		db_property_setters = frappe.get_all(
			"Property Setter",
			filters={"doc_type": doctype},
			pluck="name"
		)
		db_ps_set = set(db_property_setters)
		
		ps_to_remove = []
		for ps in data["property_setters"]:
			ps_name = ps.get("name")
			if ps_name and ps_name not in db_ps_set:
				ps_to_remove.append(ps_name)
		
		if ps_to_remove:
			log(f"\n🗑️  Found {len(ps_to_remove)} deleted property setter(s):")
			for ps_name in ps_to_remove:
				log(f"  - {ps_name}")
			
			data["property_setters"] = [
				ps for ps in data["property_setters"]
				if ps.get("name") not in ps_to_remove
			]
		
		# Clean up field_order property setter to remove:
		# 1. Fields explicitly being deleted (all_deleted_fields)
		# 2. Any orphaned custom fields that no longer exist in the custom_fields array
		# Build a set of all valid custom field FIELDNAMES currently in the JSON (after cleanup)
		# field_order uses fieldname, not name
		valid_custom_field_fieldnames = {field.get("fieldname") for field in data["custom_fields"] if field.get("fieldname")}
		
		# Get standard DocType fields to distinguish from custom fields
		try:
			dt_meta = frappe.get_meta(doctype)
			standard_field_names = {df.fieldname for df in dt_meta.fields if hasattr(df, 'fieldname')}
		except Exception:
			standard_field_names = set()
		
		log(f"DEBUG: Found {len(all_custom_field_names)} custom field fieldnames in DB")
		log(f"DEBUG: Found {len(valid_custom_field_fieldnames)} custom field fieldnames in JSON")
		log(f"DEBUG: Found {len(standard_field_names)} standard DocType fields")
		
		# Update field_order to only include valid fields
		for ps in data["property_setters"]:
			if ps.get("property") == "field_order" and ps.get("value"):
				try:
					# Parse the field_order JSON array
					field_order = json.loads(ps["value"])
					if isinstance(field_order, list):
						original_count = len(field_order)
						cleaned_field_order = []
						removed_fields = []
						
						for field_name in field_order:
							# Keep the field if it's either:
							# 1. A standard DocType field, OR
							# 2. A custom field that exists in the JSON
							if field_name in standard_field_names or field_name in valid_custom_field_fieldnames:
								cleaned_field_order.append(field_name)
							else:
								# Field doesn't exist anywhere - remove it
								removed_fields.append(field_name)
								log(f"Removing orphaned field from field_order: {field_name}")
						
						removed_count = original_count - len(cleaned_field_order)
						
						if removed_count > 0:
							log(f"DEBUG: Removed {removed_count} fields: {', '.join(removed_fields)}")
						
						if removed_count > 0:
							# Update the property setter with the cleaned field order
							ps["value"] = json.dumps(cleaned_field_order)
							log(f"Updated field_order property setter - removed {removed_count} field reference(s)")
				except (json.JSONDecodeError, TypeError):
					# If parsing fails, skip this property setter
					pass
					# If parsing fails, skip this property setter
					pass
	
	# Write back the cleaned data
	with open(file_path, "w") as f:
		json.dump(data, f, indent=1, sort_keys=False)
	
	total_removed = len(fields_to_remove) + len(fields_to_exclude or [])
	if total_removed > 0:
		log(f"\n✅ Cleaned up {doctype} JSON - processed {total_removed} field(s)")
		log(f"📁 Updated: {file_path}")
	else:
		log(f"📁 Updated: {file_path} (field_order cleanup only)")



def cleanup_all_doctypes():
	"""Cleanup all custom JSON files in the ivm module"""
	module_name = "ivm"
	custom_dir = frappe.get_app_path("ivm", module_name, "custom")
	
	if not os.path.exists(custom_dir):
		print("No custom directory found")
		return
	
	json_files = [f for f in os.listdir(custom_dir) if f.endswith(".json")]
	
	print(f"Checking {len(json_files)} custom JSON file(s)...\n")
	
	for json_file in json_files:
		# Extract doctype name from filename
		doctype_slug = json_file.replace(".json", "")
		
		# Try to find the actual DocType name
		# This is a rough conversion from slug to DocType name
		doctype = doctype_slug.replace("_", " ").title()
		
		try:
			# Verify the DocType exists
			if frappe.db.exists("DocType", doctype):
				print(f"\n--- {doctype} ---")
				cleanup_deleted_fields(doctype)
		except Exception as e:
			print(f"Error processing {doctype}: {str(e)}")


if __name__ == "__main__":
	# Allow running from bench console
	import sys
	if len(sys.argv) > 1:
		cleanup_deleted_fields(sys.argv[1])
	else:
		cleanup_all_doctypes()
