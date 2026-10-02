app_name = "ivm"
app_title = "IVM"
app_publisher = "IVM"
app_description = "IVM Integration App"
app_email = "itsupport@ivminc.com"
app_license = "mit"

# Includes in <head>
# ------------------
fixtures = [
	{
		"dt": "Issue Type",
		"filters": [
			[
				"name",
				"in",
				[
					"Change Request",
					"Reconfiguration",
					"Offboarding",
					"Onboarding",
					"Permission Change",
					"IT",
					"Desktop Support",
					"Vending Management",
					"Receivable",
					"Support",
				],
			]
		],
	},
	"Case Reason",
	{
		"dt": "Translation",
		"filters": [["source_text", "in", ["Projects", "Project", "Issue", "User Group"]]],
	},
	"Connectivity Type",
	"Card Reader Type",
	{
		"dt": "List View Settings",
		"filters": [["name", "in", ["Issue", "Project", "Warehouse Request", "Version", "Lead"]]],
	},
	{
		"dt": "Workflow Action Master",
		"filters": [
			[
				"name",
				"in",
				[
					"Approve",
					"Reject",
					"Review",
					"Set As Beginning Stage",
					"Set As Active Dialogue",
					"Set As Pending Contract",
					"Set As Contract Sent",
					"Set As Redline/PO",
					"Set As Closed Lost",
					"Set As Closed Won",
				],
			]
		],
	},
	{
		"dt": "Custom DocPerm",
		"filters": [
			[
				"role",
				"in",
				[
					"CEO",
					"COO",
					"CTO",
					"Graphic Designer",
					"Integration",
					"ITAdmin",
					"Management",
					"Operations",
					"President",
					"Regional Sales Director",
					"S&I Manager",
					"Sales Representatives",
					"Support",
					"Warehouse",
					"Technician",
				],
			]
		],
	},
	{"dt": "Workflow", "filters": [["document_type", "=", "Opportunity"]]},
	{
		"dt": "Workflow State",
		"filters": [
			[
				"name",
				"in",
				[
					"Pending",
					"Approved",
					"Rejected",
					"Active Dialogue",
					"Pending Contract",
					"Contract Sent",
					"Redline/PO",
					"Closed Won",
					"Closed Lost",
					"Beginning Stages",
					"Discovery",
				],
			]
		],
	},
	{
		"dt": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"CEO",
					"COO",
					"CTO",
					"Graphic Designer",
					"Integration",
					"ITAdmin",
					"Management",
					"Operations",
					"President",
					"Regional Sales Director",
					"S&I Manager",
					"Sales Representatives",
					"Support",
					"Warehouse",
					"Technician",
				],
			]
		],
	},
	{
		"dt": "Project Type",
		"filters": [["name", "in", ["Internal", "Other", "External", "Deployment"]]],
	},
	"CRM Pipeline",
	{
		"dt": "CRM Deal Status",
		"filters": [
			[
				"name",
				"in",
				[
					"Lost",
					"On-Hold / Timing",
					"Discovery",
					"Solution Design",
					"Presentation",
					"Contracting",
					"Due Diligence",
					"Proposal & Pricing",
					"RFP / Decision TBD",
					"Won",
				],
			]
		],
	},
	{
		"dt": "Server Script",
		"filters": [["module", "=", "IVM"]],
	},
	{
		"dt": "Client Script",
		"filters": [["module", "=", "IVM"]],
	},
	{"dt": "Workspace", "filters": [["module", "is", "not set"], ["app", "is", "not set"]]},
	# NOTE: "Workspace Shortcut" is intentionally NOT declared as its own top-level
	# fixture here. Workspace's own fixture export already embeds its full
	# "shortcuts" child table via as_dict(), so a separate standalone declaration
	# would cause every sync_fixtures() call to insert two full copies of every
	# shortcut (see ivm.patches.dedupe_workspace_shortcuts for the historical fix).
	{"dt": "Desktop Icon", "filters": [["standard", "=", 0]]},
	{
		"dt": "Workspace Sidebar",
		"filters": [
			[
				"name",
				"in",
				[
					"Change Request",
					"Clients",
					"Deployments",
					"Desktop Support",
					"IT",
					"Offboarding",
					"Onboarding",
					"Permission Change",
					"Receivable",
					"Reconfiguration",
					"Support Queue",
					"Vending Management",
					"Warehouse Management",
					"Warehouse Requests",
					"Warehousing",
				],
			]
		],
	},
	{"dt": "Print Format", "filters": [["standard", "=", "No"]]},
	{
		"dt": "Report",
		"filters": [
			["is_standard", "=", "No"],
			["name", "not in", ["Q3 2022", "Current Quarter Metrics", "Test 2", "Test 3"]],
		],
	},
	{"dt": "CRM Fields Layout", "filters": [["dt", "=", "CRM Deal"]]},
	{"dt": "CRM Form Script", "filters": [["dt", "=", "CRM Deal"], ["is_standard", "=", 0]]},
	{"dt": "Assignment Rule", "filters": [["name", "=", "Warehouse Request Assignment"]]},
	{
		"dt": "Notification",
		"filters": [["name", "in", ["Shipping Warehouse", "Warehouse Request Resolved/Closed Notification"]]],
	},
]

# include js, css files in header of desk.html
app_include_css = [
	"/assets/ivm/css/chatbox_widget.css",
	"/assets/ivm/css/embedded_form.css",
	"/assets/ivm/css/project.css",
]

app_include_js = [
	# "/assets/ivm/js/workspace.js","/assets/ivm/js/awesome_bar.js",
	"/assets/ivm/js/utils.js",
	"/assets/ivm/js/embedded_form.js",
	"/assets/ivm/js/chatbox_widget.js",
	"/assets/ivm/js/barcode_scanner_override.js",
	"/assets/ivm/js/machine_detail_grids.js",
]

# include js, css files in header of web template
# web_include_css = "/assets/ivm/css/ivm.css"
# web_include_js = "/assets/ivm/js/ivm.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "ivm/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
doctype_js = {
	"Customer": "public/js/doctype/Customer.js",
	"Task": "public/js/doctype/Task.js",
	"CRM Deal": "public/js/doctype/CRM_Deal.js",
	"Project": "public/js/doctype/Project.js",
	"Issue": "public/js/doctype/Issue.js",
	"Delivery Note": "public/js/doctype/Delivery_Note.js",
	"Stock Entry": "public/js/doctype/Stock_Entry.js",
	"Pick List": "public/js/doctype/Pick_List.js",
}

doctype_list_js = {
	# "Lead": "public/js/listview/Lead_listview.js",
	# "Opportunity": "public/js/listview/Opportunity_listview.js",
	"Customer": "public/js/listview/Customer_listview.js",
	"User": "public/js/listview/user_listview.js",
	"Calendar Events": "public/js/calendar.js",
	# "Project": "public/js/listview/project_listview.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# portal home page resolution (see ivm/client_portal/utils/home_page.py)
get_website_user_home_page = "ivm.client_portal.utils.home_page.get_website_user_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

jinja = {
	"methods": ["ivm.warehouse.services.warehouse_request.render_machine_details_html"],
}

# Installation
# ------------

# before_install = "ivm.install.before_install"
# after_install = "ivm.install.after_install"


# Uninstallation
# ------------

# before_uninstall = "ivm.uninstall.before_uninstall"
# after_uninstall = "ivm.uninstall.after_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ivm.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# "Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# "Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Email Account": "ivm.support.overrides.CustomEmailAccount",
}
# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"User": {
		"before_validate": "ivm.client_portal.event_handlers.user.enforce_portal_user_roles",
	},
	"Communication": {
		"on_update": "ivm.support.event_handlers.communication.on_update",
	},
	"Item": {"before_save": "ivm.warehouse.event_handlers.item.before_save"},
	"Wiki Document": {
		"on_update": "ivm.integrations.wiki.content_webhook.on_wiki_document_update",
	},
	"CRM Deal": {
		"on_update": "ivm.deployments.event_handlers.deal.on_update",
		"before_test_insert": "ivm.deployments.event_handlers.deal.ensure_deployment_location_for_test",
	},
	"Project": {
		"before_validate": "ivm.deployments.event_handlers.project.before_validate",
		"validate": "ivm.deployments.event_handlers.project.validate",
		# "after_insert": "ivm.deployments.event_handlers.project.after_insert",
	},
	"Stock Entry": {
		"after_insert": "ivm.warehouse.event_handlers.stock_entry.after_insert",
		"on_submit": "ivm.warehouse.event_handlers.stock_entry.on_submit",
	},
	"Service Quote": {
		"on_submit": "ivm.client_portal.event_handlers.service_quote.on_submit",
	},
}

# Website Permissions
# -------------------

has_website_permission = {
	"Service Quote": "ivm.client_portal.doctype.service_quote.service_quote.has_website_permission",
}

# Website Routes
# ---------------

website_route_rules = [
	{"from_route": "/service-quotes/<path:name>", "to_route": "service_quote"},
]

# Scheduled Tasks
# ---------------

scheduler_events = {
	# "all": [
	# "ivm.tasks.all"
	# ],
	# "daily": [
	# "ivm.tasks.daily"
	# ],
	"hourly": [
		# Catch inbound reply emails that HubSpot does not surface via webhooks.
		"ivm.integrations.hubspot.scheduled_tasks.sync_inbound_emails",
	],
	# "weekly": [
	# "ivm.tasks.weekly"
	# ],
	# "monthly": [
	# "ivm.tasks.monthly"
	# ],
	"cron": {
		"0/15 * * * *": [
			"ivm.integrations.hubspot.reconciler.reconcile",
		],
	},
}

# Testing
# -------

# before_tests = "ivm.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
	"frappe.desk.search.get_value": "ivm.machine_hardware_management.overrides.virtual_get_value.virtual_get_value",
	"frappe.realtime.has_permission": "ivm.overrides.realtime_permission.has_permission",
}
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
override_doctype_dashboards = {
	"Issue": "ivm.api.get_data",
	"Project": "ivm.api.override_project_dashboard",
}

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["ivm.utils.before_request"]
# after_request = ["ivm.utils.after_request"]

# Job Events
# ----------
# before_job = ["ivm.utils.before_job"]
# after_job = ["ivm.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# {
# "doctype": "{doctype_1}",
# "filter_by": "{filter_by}",
# "redact_fields": ["{field_1}", "{field_2}"],
# "partial": 1,
# },
# {
# "doctype": "{doctype_2}",
# "filter_by": "{filter_by}",
# "partial": 1,
# },
# {
# "doctype": "{doctype_3}",
# "strict": False,
# },
# {
# "doctype": "{doctype_4}"
# }
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# "ivm.auth.validate"
# ]
