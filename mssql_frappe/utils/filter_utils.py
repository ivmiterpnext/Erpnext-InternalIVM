import re
from datetime import datetime, date
from urllib.parse import urlencode
from mssql_frappe.utils.case_utils import to_camel_case
from mssql_frappe.mssql_frappe.doctype.machine_link.machine_link import get_machine_name_from_machine_id

_LIKE_META = re.compile(r'([.^$+?{}[\]\\|()])')  # escape regex metachars

def _to_list(val):
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        return [str(v) for v in val]
    # comma-separated string
    return [s.strip() for s in str(val).split(',') if s.strip()]

def _coerce(v):
    # normalize None/empty
    if v in (None, ''):
        return None
    # try numeric
    try:
        if isinstance(v, str) and v.isdigit():
            return int(v)
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            # try float
            return float(v)
    except Exception:
        pass
    # try datetime
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m-%d-%Y", "%m-%d-%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(str(v), fmt)
            return dt
        except Exception:
            pass
    # fallback to case-insensitive string
    return str(v).lower()

def _like_to_regex(pattern: str) -> re.Pattern:
    s = str(pattern or '')
    # escape regex metachars first
    s = _LIKE_META.sub(r'\\\1', s)
    # SQL LIKE: % any run, _ single char
    s = s.replace('%', '.*').replace('_', '.')
    return re.compile(s, re.IGNORECASE)

def match_filter(item, flt):
    # flt format: [doctype, field, op, value]
    try:
        _, field, op, value = flt
    except Exception:
        return True
    field = str(field).lower().replace(' ', '_')
    item_val = item.get(field)
    op = str(op or '').lower()

    # normalize
    a = _coerce(item_val)
    b = _coerce(value)

    if op in ('=', '=='):
        return a == b
    if op in ('!=', '<>'):
        return a != b
    if op == '>':
        return (a is not None and b is not None) and a > b
    if op == '>=':
        return (a is not None and b is not None) and a >= b
    if op == '<':
        return (a is not None and b is not None) and a < b
    if op == '<=':
        return (a is not None and b is not None) and a <= b
    if op == 'between':
        # value expected: [lo, hi]
        try:
            lo, hi = value
            lo = _coerce(lo)
            hi = _coerce(hi)
            return (a is not None and lo is not None and hi is not None) and (lo <= a <= hi)
        except Exception:
            return True
    if op == 'like':
        regex = _like_to_regex(str(value))
        return bool(regex.search(str(item_val or '')))
    if op == 'not like':
        regex = _like_to_regex(str(value))
        return not bool(regex.search(str(item_val or '')))
    if op == 'in':
        return str(item_val).lower() in [s.lower() for s in _to_list(value)]
    if op == 'not in':
        return str(item_val).lower() not in [s.lower() for s in _to_list(value)]
    if op == 'is':
        # support 'set'/'not set' or 'null'/'not null'
        val = str(value).lower()
        if val in ('set', 'not null'):
            return item_val not in (None, '')
        if val in ('not set', 'null'):
            return item_val in (None, '')
    # fallback: don’t filter it out
    return True


def _norm_sort_val(v):
    # None sorts last
    if v is None:
        return (1, '')
    # numbers sort before strings when mixed
    if isinstance(v, (int, float)):
        return (0, v)
    # datetimes / dates – stringify ISO safely
    try:
        if isinstance(v, (date, datetime)):
            return (0, v.isoformat())
    except Exception:
        pass
    # strings – lowercased for case-insensitive sort
    return (0, str(v).lower())

def apply_multi_field_sort(result, order_by):
    if not order_by:
        return result
    sort_fields = [s.strip() for s in str(order_by).split(',') if s.strip()]
    sort_instructions = []
    for sort_field in sort_fields:
        parts = sort_field.rsplit(' ', 1)
        if len(parts) == 2:
            field_part, direction = parts
            field = field_part.split('.')[-1].replace('`', '')
            field_snake = field.lower().replace('-', '_')
            reverse = direction.lower() == 'desc'
            sort_instructions.append((field_snake, reverse))
    # stable multi-key sort: last key first
    for field_snake, reverse in reversed(sort_instructions):
        result.sort(key=lambda x: _norm_sort_val(x.get(field_snake)), reverse=reverse)
    return result

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
            # backend search param without wildcards
            params[field_camel] = str(value).replace('%', '').replace('_', '')
        elif op in ('in', 'not in'):
            vals = _to_list(value)
            if vals:
                params[field_camel] = ','.join(vals)
                # if you need to express 'not in', add a sibling like field_camel + 'NotIn' = 1
        elif op in ('>=', '>', '<=', '<'):
            # if your API supports range suffixes, adapt here:
            suffix = {'>=': 'Gte', '>': 'Gt', '<=': 'Lte', '<': 'Lt'}[op]
            params[field_camel + suffix] = value
        elif op == 'between':
            try:
                lo, hi = value
                params[field_camel + 'Start'] = lo
                params[field_camel + 'End'] = hi
            except Exception:
                pass
        # else: ignore; you can still filter client-side
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
