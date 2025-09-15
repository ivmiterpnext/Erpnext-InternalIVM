def set_attrs_from_dict(obj, data, child_table_map=None):
    child_table_map = child_table_map or {}
    doctype_name = obj.doctype.lower()

    for k, v in (data or {}).items():
        mapped_key = f"{doctype_name}_name" if k == "name" else k

        if mapped_key in child_table_map:
            child_field = child_table_map[mapped_key]
            rows = normalize_child_table_field(v, child_field)
            obj.set(mapped_key, rows)
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
