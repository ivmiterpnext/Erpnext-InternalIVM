import os
import frappe


def get_list_cache_expires():
    try:
        return int(os.environ.get("LIST_CACHE_EXPIRES"))
    except (TypeError, ValueError):
        return 300

LIST_CACHE_EXPIRES = get_list_cache_expires()

def clear_cache_by_prefix(prefix):
    cache = None

    try:
        cache = frappe.cache()
    except ImportError:
        return

    if cache:
        for key in cache.keys(f"{prefix}*"):
            cache.delete_key(key)
            frappe.logger().info(f"Cache key deleted: {key}")
