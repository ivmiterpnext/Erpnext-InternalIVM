def apply_multi_field_sort(result, order_by):
    print("\napply multi field sort called\n", flush=True)
    if not order_by:
        return result
    sort_fields = [s.strip() for s in order_by.split(',')]
    sort_instructions = []
    for sort_field in sort_fields:
        parts = sort_field.rsplit(' ', 1)
        if len(parts) == 2:
            field_part, direction = parts
            if '.' in field_part:
                field = field_part.split('.')[-1].replace('`', '')
            else:
                field = field_part.replace('`', '')
            field_snake = field.lower().replace('-', '_')
            reverse = direction.lower() == "desc"
            sort_instructions.append((field_snake, reverse))
    for field_snake, reverse in reversed(sort_instructions):
        result.sort(key=lambda x: x.get(field_snake), reverse=reverse)
    return result


def match_filter(item, filter):
    print("\nmatch_filter called\n", flush=True)
    _, field, op, value = filter
    field = field.lower().replace(' ', '_')
    item_val = item.get(field)
    if op == '=':
        return str(item_val) == str(value)
    elif op == '!=':
        return str(item_val) != str(value)
    elif op == 'like':
        # Convert both to string and lower for case-insensitive match
        item_val_str = str(item_val or '').lower()
        pattern = str(value or '').lower()
        # Replace SQL wildcards with Python wildcards
        pattern = pattern.replace('%', '.*')
        import re
        return re.fullmatch(pattern, item_val_str) is not None or pattern.strip('.*') in item_val_str
    elif op == 'not like':
        return value.replace('%', '') not in str(item_val)
    elif op == 'in':
        return str(item_val) in value
    elif op == 'not in':
        return str(item_val) not in value
    else:
        return True  # fallback: do not filter out
    
    
def filters_to_query_params(filters):
    from urllib.parse import urlencode
    from mssql_frappe.utils.case_utils import to_camel_case

    params = {}
    for flt in filters or []:
        if len(flt) == 4:
            _, field, operation, value = flt
            camel_field = to_camel_case(field)

            if operation == '=':
                params[camel_field] = value

            elif operation  == 'like':
                params[camel_field] = value.replace('%', '')

            elif operation.lower() == 'between':

                if field.lower() == "creation":
                    params["createdRangeStartDate"] = value[0]
                    params["createdRangeEndDate"] = value[1]

            # Add more operators as needed
    return urlencode(params)

def dict_filters_to_query_params(filters):
    """
    Converts a dict of filters to a query string with camelCase keys.
    Example: {"board_manufacturer_id": 3} -> "boardManufacturerId=3"
    """
    from urllib.parse import urlencode
    from mssql_frappe.utils.case_utils import to_camel_case

    if not filters or not isinstance(filters, dict):
        return ""
    params = {to_camel_case(str(k)): v for k, v in filters.items() if v is not None}
    return urlencode(params)