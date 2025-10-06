import os
import frappe

LIST_CACHE_EXPIRES = int(os.environ.get("LIST_CACHE_EXPIRES", 300))

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
