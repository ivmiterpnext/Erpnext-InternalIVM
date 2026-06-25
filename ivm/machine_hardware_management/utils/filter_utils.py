import re
from datetime import datetime, date
from urllib.parse import urlencode
from ivm.integrations.icorp.utils import to_camel_case
from ivm.machine_hardware_management.doctype.machine_link.machine_link import get_machine_name_from_machine_id

_LIKE_META = re.compile(r'([.^$+?{}[\]\\|()])')  # escape regex metachars

DEFAULT_FIELD_MAP = {
    "creation": "createdDate",
    "modified": "modifiedDate",
}

def _to_list(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(v) for v in val]

    return [s.strip() for s in str(val).split(',') if s.strip()]

def filters_to_query_params(filters):
    params = {}
    for flt in filters or []:
        if len(flt) != 4:
            continue
        _, field, op, value = flt
        field_camel = to_camel_case(str(field))
        op = str(op or '').lower()

        if op in ('=', '=='):
            params[field_camel] = value

        elif op == 'like':
            params[field_camel] = str(value).replace('%', '').replace('_', '')

        elif op in ('in', 'not in'):
            vals = _to_list(value)
            if vals:
                params[field_camel] = ','.join(vals)

        elif op in ('>=', '>', '<=', '<'):

            suffix = {'>=': 'Gte', '>': 'Gt', '<=': 'Lte', '<': 'Lt'}[op]
            params[field_camel + suffix] = value

        elif op == 'between':
            try:
                lo, hi = value
                params[field_camel + 'Start'] = lo
                params[field_camel + 'End'] = hi
            except Exception:
                pass

    return urlencode(params)

def replace_machine_id_with_name(filters):
    new_filters = []
    for f in filters or []:
        if (
            isinstance(f, (list, tuple))
            and len(f) >= 4
            and f[1] == "machine_id"
        ):
            machine_name = get_machine_name_from_machine_id(f[3])
            if machine_name:
                new_filters.append((f[0], "machine_name", f[2], machine_name))
            else:
                new_filters.append(f)
        else:
            new_filters.append(f)
    return new_filters

def frappe_filters_to_dict(filters, field_map=None):
    # Merge default and provided field_map
    merged_map = {**DEFAULT_FIELD_MAP, **(field_map or {})}
    params = {}
    for flt in filters or []:
        if len(flt) != 4:
            continue
        _, field, op, value = flt
        field = merged_map.get(field, field)
        field_camel = to_camel_case(str(field))
        op = str(op or '').lower()

        if op in ('=', '=='):
            params[field_camel] = value

        elif op == 'like':
            params[field_camel] = str(value).replace('%', '').replace('_', '')

        elif op in ('in', 'not in'):
            vals = _to_list(value)
            if vals:
                params[field_camel] = ','.join(vals)

        elif op in ('>=', '>', '<=', '<'):
            suffix = {'>=': 'Gte', '>': 'Gt', '<=': 'Lte', '<': 'Lt'}[op]
            params[field_camel + suffix] = value

        elif op == 'between':
            try:
                lo, hi = value
                params[field_camel + 'Start'] = lo
                params[field_camel + 'End'] = hi
            except Exception:
                pass
    return params

def frappe_sort_to_dict(order_by, field_map=None):
    if not order_by:
        return {}

    # Regex to match: `table name`.`field` direction
    match = re.match(r"(?:`[^`]+`\.)?`?([^` ]+)`?\s*(asc|desc)?", order_by, re.IGNORECASE)
    if match:
        field = match.group(1)
        direction = match.group(2) or "asc"
    else:
        # Fallback: split by space
        parts = order_by.split()
        field = parts[0].replace('`', '')
        if '.' in field:
            field = field.split('.')[-1]
        direction = parts[1] if len(parts) > 1 else "asc"

    merged_map = {**DEFAULT_FIELD_MAP, **(field_map or {})}
    field = merged_map.get(field, field)
    field_camel = to_camel_case(str(field))
    direction = direction.lower()
    if direction not in ("asc", "desc"):
        direction = "asc"
    return {"sortField": field_camel, "sortOrder": direction}
