import frappe


def execute():
	"""
	Workspace Shortcut was declared as its own top-level fixture in hooks.py
	*in addition* to Workspace itself. Since Workspace's own fixture export
	already embeds its full "shortcuts" child table, every sync_fixtures()
	call inserted two complete copies of every shortcut: one via the parent
	Workspace's own child-table insert cascade, and one via the redundant
	standalone Workspace Shortcut fixture. Because child-table rows always
	get a freshly generated name on insert (Workspace Shortcut has no
	autoname rule), neither insert path ever matched or replaced the other,
	so every migrate doubled the record count. This has been running since
	Workspace Shortcut was first added to fixtures, compounding on every
	migrate since.

	This patch collapses all exact-duplicate Workspace Shortcut rows
	(same parent + same content) down to a single surviving row per group,
	keeping the oldest by creation. The redundant standalone fixture
	declaration has been removed from hooks.py separately so this doesn't
	recur.
	"""

	frappe.db.sql(
		"""
		DELETE ws1 FROM `tabWorkspace Shortcut` ws1
		INNER JOIN `tabWorkspace Shortcut` ws2
			ON ws1.parent = ws2.parent
			AND COALESCE(ws1.type, '') = COALESCE(ws2.type, '')
			AND COALESCE(ws1.link_to, '') = COALESCE(ws2.link_to, '')
			AND COALESCE(ws1.url, '') = COALESCE(ws2.url, '')
			AND COALESCE(ws1.doc_view, '') = COALESCE(ws2.doc_view, '')
			AND COALESCE(ws1.label, '') = COALESCE(ws2.label, '')
			AND COALESCE(ws1.icon, '') = COALESCE(ws2.icon, '')
			AND COALESCE(ws1.stats_filter, '') = COALESCE(ws2.stats_filter, '')
			AND COALESCE(ws1.color, '') = COALESCE(ws2.color, '')
			AND COALESCE(ws1.format, '') = COALESCE(ws2.format, '')
			AND COALESCE(ws1.kanban_board, '') = COALESCE(ws2.kanban_board, '')
			AND COALESCE(ws1.report_ref_doctype, '') = COALESCE(ws2.report_ref_doctype, '')
		WHERE
			ws1.creation > ws2.creation
			OR (ws1.creation = ws2.creation AND ws1.name > ws2.name)
		"""
	)

	frappe.db.commit()
