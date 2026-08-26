"""Override for frappe.realtime.has_permission.

Suppresses DoesNotExistError when the Socket.IO server checks permission
for a client-side local/unsaved document name (e.g. "new-issue-abc1234xyz").

This is a Frappe core bug: form.js switch_doc() calls
setup_docinfo_change_listener() (which subscribes to realtime) before
this.doc is reassigned to the new document, so is_new() checks the
*previous* document's __islocal flag — when the previous doc was a saved
record and the new doc is unsaved, the guard passes incorrectly and a
doc_subscribe fires for the local-only name, which doesn't exist in the DB.

See: https://github.com/frappe/frappe/issues/16726
"""

import re
import frappe


_LOCAL_DOC_NAME = re.compile(r"^new-[a-z0-9-]+-[a-z0-9]{10}$")


@frappe.whitelist(allow_guest=True)
def has_permission(doctype: str, name: str) -> bool:
    if _LOCAL_DOC_NAME.match(name):
        # Unsaved client-side doc — no DB row exists, nothing to subscribe to.
        # Return False so the socket.io handler's promise never resolves
        # (socket silently does not join the room). Identical end-user effect
        # to the current behavior, minus the Error Log entry.
        return False
    frappe.has_permission(doctype, doc=name, throw=True)
    return True
