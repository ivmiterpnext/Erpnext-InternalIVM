import frappe


@frappe.whitelist()
def get_child_table_row(
	doctype: str,
	name: str,
	host_doctype: str | None = None,
	host_name: str | None = None,
) -> dict:
	"""
	Fetch a single child table row as a dict.
	Needed because child table records (istable=1) are not served via the
	standard frappe.model.with_doc / frappe.get_doc client API.

	Permission is checked against the "host" document the caller is
	embedding this row into (host_doctype/host_name), when provided —
	e.g. the Warehouse Request the row's snapshot is being displayed on —
	rather than the row's own true parent record. This avoids conflating
	"can view this embedded read-only snapshot on a document I'm already
	permitted to read" with "can independently read the source record
	(e.g. Project) this data happened to be copied from."

	Falls back to checking permission against the row's own parent when no
	host is supplied, preserving the original behavior for any other caller.
	"""
	meta = frappe.get_meta(doctype)
	if not meta.istable:
		frappe.throw(f"{doctype} is not a child table DocType.")

	row = frappe.get_doc(doctype, name)

	if host_doctype and host_name:
		frappe.has_permission(host_doctype, "read", host_name, throw=True)
	elif row.parenttype and row.parent:
		frappe.has_permission(row.parenttype, "read", row.parent, throw=True)

	return row.as_dict()
