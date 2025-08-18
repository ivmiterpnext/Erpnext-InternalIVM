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

def api_items_to_frappe_dict(items, name_field):
    import frappe

    result = []
    for item in items:
        d = frappe._dict({k: v for k, v in item.items()})
        d.name = str(item[name_field])
        result.append(d)
        
    return result


def api_items_to_frappe_dict(items, name_field, search_txt=None):
    import frappe

    result = []
    for item in items:

        d = frappe._dict({k: v for k, v in item.items()})
        d.name = str(item[name_field])

        # # Filter here if search_txt is provided
        # if search_txt:
        #     if d.text and search_txt.lower() not in d.text.lower():
        #         continue
        result.append(d)
    return result