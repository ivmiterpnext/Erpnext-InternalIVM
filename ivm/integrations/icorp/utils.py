"""Case-conversion and data-mapping helpers for iCorp API integration."""

import re

import frappe


def to_camel_case(s: str) -> str:
    """Convert a snake_case string to camelCase."""
    parts = s.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])


def dict_keys_to_camel_case(d: dict) -> dict:
    """Convert all top-level dict keys from snake_case to camelCase."""
    return {to_camel_case(k): v for k, v in d.items()}


def dict_keys_to_snake_case(obj: dict | list):
    """Recursively convert all dict keys from camelCase to snake_case."""
    def camel_to_snake(name: str) -> str:
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    if isinstance(obj, dict):
        return {camel_to_snake(k): dict_keys_to_snake_case(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [dict_keys_to_snake_case(i) for i in obj]
    return obj


def api_data_to_frappe_dict(data: list[dict], key_field: str) -> list[frappe._dict]:
    """Convert a list of API response dicts to ``frappe._dict`` objects.

    Sets ``.name`` on each dict from the value of *key_field* so the
    results can be used directly in Frappe list views.
    """
    result = []
    for item in (data or []):
        d = frappe._dict(item)
        d.name = str(item.get(key_field))
        result.append(d)
    return result


def convert_fields_to_bool(data: dict, field_names: list[str]) -> dict:
    """Coerce the specified fields in *data* to ``bool`` in-place.

    Handles string values like ``"1"``, ``"true"``, ``"yes"`` as truthy.
    """
    for k in field_names:
        v = data.get(k)
        if isinstance(v, str):
            data[k] = v.lower() in ('1', 'true', 'yes')
        else:
            data[k] = bool(v)
    return data
