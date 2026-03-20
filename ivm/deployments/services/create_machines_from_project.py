import frappe

def create_machines_from_project(project, method=None):

    for table in get_child_tables("Project"):
        for row in getattr(project, table, []):
            machine_data = {
                "doctype": "Machine",
                "machine_name": row.machine_name,
                "location_id": project.location_id, #TODO: location id is not currently on project, what do we do about this
                "client_id": project.client_id,
                "machine_type_id": row.machine_type_id,
                "machine_purpose_id": row.machine_purpose_id,
                "machine_status_type_code": "B",
                "time_zone_id": project.time_zone_id, # Double check

                #TODO: Do we also set up any board information?
            }
            frappe.get_doc(machine_data).insert(ignore_permissions=True)

def get_child_tables(parent_doctype):
    meta = frappe.get_meta(parent_doctype)
    return [df.fieldname for df in meta.fields if df.fieldtype == "Table"]
