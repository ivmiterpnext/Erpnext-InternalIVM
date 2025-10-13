from datetime import datetime
import frappe
from mssql_frappe.utils.case_utils import to_camel_case

def get_primary_order_by(order_by):
    if not order_by:
        return ""
    parts = [part.strip() for part in order_by.split(',') if part.strip()]
    return parts[0] if parts else ""

def build_sort_params(order_by, sort_field_map):
    sort_field_map = {**sort_field_map, 'creation': 'createdDate'}
    sort_params = []
    # Only use the most recent (last) order_by field
    primary_order_by = get_primary_order_by(order_by)
    if not primary_order_by:
        return []
    part = primary_order_by
    # Remove table prefix and backticks
    if part.startswith('`'):
        part = part.split('`.', 1)[-1]
    if ' ' in part:
        field, direction = part.rsplit(' ', 1)
    else:
        field, direction = part, 'asc'
    api_field = sort_field_map.get(field, to_camel_case(field))
    sort_params.append(("sort[0].parameterName", api_field))
    sort_params.append(("sort[0].sortOrder", direction.upper()))
    return sort_params

def set_attrs_from_dict(obj, data, child_map: dict[str, str] | None = None):
	child_map = child_map or {}
	data = data or {}

	for key, val in data.items():
		# Child / Table MultiSelect field?
		if key in child_map:
			attach_children(obj, key, val, child_map[key])
			continue

		# Normalize common "id" scalars to strings
		if key.endswith("id") and not isinstance(val, (list, dict)):
			val = "" if val is None else str(val)

		# Assign directly (uses BaseDocument.set under the hood)
		obj.set(key, val)

	# Normalize empty strings on the doc to None (optional, keeps Desk clean)
	for f in list(obj.__dict__):
		if getattr(obj, f) == "":
			setattr(obj, f, None)


def attach_children(doc, fieldname: str, values, child_link_field: str):
	meta = frappe.get_meta(doc.doctype)
	df = meta.get_field(fieldname)
	if not df:
		frappe.throw(f"Field '{fieldname}' not found on {doc.doctype}")

	child_dt = df.options 
	link_field = getattr(df, "link_field", None) or child_link_field

	if not child_dt:
		frappe.throw(f"Child DocType options missing for field '{fieldname}' on {doc.doctype}")
	if not link_field:
		frappe.throw(f"Link field not set for Table MultiSelect '{fieldname}' on {doc.doctype}")

	# Normalize values
	if values is None:
		values = []
	elif not isinstance(values, list):
		values = [values]

	children = []
	for i, val in enumerate(values, start=1):
		payload = val if isinstance(val, dict) else {link_field: ("" if val is None else str(val))}
		cd = frappe.get_doc({"doctype": child_dt})
		cd.update(payload)
		cd.parent = doc.name
		cd.parenttype = doc.doctype
		cd.parentfield = fieldname
		cd.idx = i
		children.append(cd)

	# Important for virtual doctypes: bypass child-table mutation path
	doc.set(fieldname, children, as_value=True)




# def normalize_child_table_field(value, child_field):
#     rows = []

#     if isinstance(value, list) and value and isinstance(value[0], dict):
#         values = [str(x.get(child_field, "")) for x in value]
#     else:
#         values = [str(x) for x in (value or [])]

#     for i, val in enumerate(values, start=1):
#         rows.append({
#             child_field: val,
#             "idx": i
#         })

#    return rows

def to_iso8601(date_string):
    for input_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed_datetime = datetime.strptime(date_string, input_format)
            return parsed_datetime.isoformat(timespec="seconds")
        except Exception as e:
            frappe.log_error(f"Failed to parse date string: {e}", "DateTimeHelper.to_iso8601 error")
    return date_string
