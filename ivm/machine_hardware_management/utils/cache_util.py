import os
import frappe


def get_list_cache_expires():
    try:
        return int(os.environ.get("LIST_CACHE_EXPIRES"))
    except Exception:
        return 300

LIST_CACHE_EXPIRES = get_list_cache_expires()

def clear_cache(doctype_name):
    try:
        cache = frappe.cache()
    except Exception:
        return

    if not cache:
        return

    prefixes = [
        f"{doctype_name.lower()}_list_cache_",
        f"{doctype_name.lower()}_count_cache_"
    ]
    for prefix in prefixes:
        for key in cache.keys(f"{prefix}*"):
            cache.delete_key(key)
            frappe.logger().info(f"Cache key deleted: {key}")
