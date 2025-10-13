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

def set_attrs_from_dict(obj, data, child_table_map=None):
    child_table_map = child_table_map or {}
    doctype_name = obj.doctype.lower()

    for k, v in (data or {}).items():
        mapped_key = f"{doctype_name}_name" if k == "name" else k

        if mapped_key in child_table_map:
            child_field = child_table_map[mapped_key]
            rows = normalize_child_table_field(v, child_field)
            obj.set(mapped_key, [frappe._dict(row) for row in rows])
            continue

        if mapped_key.endswith("id") and not isinstance(v, (list, dict)):
            v = "" if v is None else str(v)
        elif not isinstance(v, (str, int, float, bool, type(None), list, dict)):
            v = str(v)

        setattr(obj, mapped_key, v)

def normalize_child_table_field(value, child_field):
    rows = []

    if isinstance(value, list) and value and isinstance(value[0], dict):
        values = [str(x.get(child_field, "")) for x in value]
    else:
        values = [str(x) for x in (value or [])]

    for i, val in enumerate(values, start=1):
        rows.append({
            child_field: val,
            "idx": i
        })

    return rows

def to_iso8601(date_string):
    for input_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed_datetime = datetime.strptime(date_string, input_format)
            return parsed_datetime.isoformat(timespec="seconds")
        except Exception as e:
            frappe.log_error(f"Failed to parse date string: {e}", "DateTimeHelper.to_iso8601 error")
    return date_string
