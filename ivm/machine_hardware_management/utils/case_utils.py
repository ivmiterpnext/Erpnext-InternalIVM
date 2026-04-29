import re
import frappe

def to_camel_case(s):
    parts = s.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])

def dict_keys_to_camel_case(d):
    return {to_camel_case(k): v for k, v in d.items()}

def dict_keys_to_snake_case(obj):
    def camel_to_snake(name):
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    if isinstance(obj, dict):
        return {camel_to_snake(k): dict_keys_to_snake_case(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [dict_keys_to_snake_case(i) for i in obj]
    return obj

def api_data_to_frappe_dict(data, key_field):
    result = []

    for item in (data or []):
        d = frappe._dict(item)
        rid = str(item.get(key_field))
        d.name = rid
        result.append(d)
    return result

def convert_fields_to_bool(data, field_names):
    for k in field_names:
        v = data.get(k)
        if isinstance(v, str):
            data[k] = v.lower() in ('1', 'true', 'yes')
        else:
            data[k] = bool(v)
    return data
