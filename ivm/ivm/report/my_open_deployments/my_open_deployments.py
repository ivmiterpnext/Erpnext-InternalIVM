import frappe


def execute(filters=None):
	columns = [
		{"label": "ID", "fieldname": "name", "fieldtype": "Link", "options": "Project", "width": 120},
		{"label": "Project Name", "fieldname": "project_name", "fieldtype": "Data", "width": 200},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": "Stage", "fieldname": "stage", "fieldtype": "Data", "width": 120},
		{"label": "Client ID", "fieldname": "client_id", "fieldtype": "Data", "width": 120},
		{"label": "Machine Numbers", "fieldname": "machine_numbers", "fieldtype": "Data", "width": 150},
		{"label": "Opportunity Term", "fieldname": "opportunity_term", "fieldtype": "Data", "width": 120},
		{"label": "Assigned To", "fieldname": "assigned_to", "fieldtype": "Data", "width": 150},
	]

	data = frappe.db.sql("""
		SELECT
			p.name,
			p.project_name,
			p.status,
			p.stage,
			p.client_id,
			p.machine_numbers,
			p.opportunity_term,
			u.full_name AS assigned_to
		FROM `tabProject` p
		JOIN `tabUser` u ON JSON_CONTAINS(COALESCE(p._assign, '[]'), JSON_QUOTE(u.name))
		WHERE u.name = %(user)s
		  AND p.status NOT IN ('Cancelled', 'Completed', 'Installed')
		ORDER BY p.modified DESC
	""", {"user": frappe.session.user}, as_dict=True)

	return columns, data
