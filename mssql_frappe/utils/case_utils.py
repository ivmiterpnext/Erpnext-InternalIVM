def to_camel_case(s):
    parts = s.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])

def dict_keys_to_camel_case(d):
    return {to_camel_case(k): v for k, v in d.items()}

def dict_keys_to_snake_case(obj):
    import re

    def camel_to_snake(name):
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    if isinstance(obj, dict):
        return {camel_to_snake(k): dict_keys_to_snake_case(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [dict_keys_to_snake_case(i) for i in obj]
    else:
        return obj

def api_items_to_frappe_dict(items, key_field, title_field=None, title_map=None):
    import frappe
    result = []
    title_map = title_map or {}

    for item in (items or []):
        d = frappe._dict(item)
        rid = str(item.get(key_field))
        d.name = rid

        title = title_map.get(rid)
        if not title and title_field and title_field in item:
            title = item.get(title_field)
        if not title:
            title = rid

        d["_title"] = title
        d["title"] = title

        result.append(d)
    return result