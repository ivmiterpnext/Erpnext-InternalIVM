app_name = "ivm"
app_title = "IVM"
app_publisher = "IVM"
app_description = "IVM Integration App"
app_email = "itsupport@ivminc.com"
app_license = "mit"

# Includes in <head>
# ------------------
fixtures = [
    "Issue Type", "Campaign", "Case Reason", "Translation", "Connectivity Type",
    "List View Settings", "Workflow Action Master", "Custom DocPerm", "Workflow", "Property Setter",
    "Workflow State", "Industry Type", "Role", "Custom Field", "Project Type", "CRM Pipeline",
    "CRM Deal Status", "Server Script", "Client Script",
    "Workspace",
    "Workspace Shortcut",
    {"dt": "Desktop Icon", "filters": [["standard", "=", 0]]},
    {"dt": "Workspace Sidebar", "filters": [["standard", "=", 0]]},
    {"dt": "Print Format", "filters": [["standard", "=", "No"]]},
    {"dt": "Report", "filters": [["is_standard", "=", "No"]]},
    {"dt": "CRM Fields Layout", "filters": [["dt", "=", "CRM Deal"]]},
]

# include js, css files in header of desk.html
app_include_css = [
    "/assets/ivm/css/chatbox_widget.css",
    "/assets/ivm/css/embedded_form.css",
    "/assets/ivm/css/project.css"
]

app_include_js = [
	# "/assets/ivm/js/workspace.js","/assets/ivm/js/awesome_bar.js",

    "/assets/ivm/js/utils.js",
    "/assets/ivm/js/embedded_form.js",
    "/assets/ivm/js/chatbox_widget.js",
    "/assets/ivm/js/barcode_scanner_override.js",
    "/assets/ivm/js/machine_detail_grids.js"
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
    # "Opportunity": "public/js/doctype/Opportunity.js",
    "Customer": "public/js/doctype/Customer.js",
    "User": "public/js/doctype/user.js",
    "Task": "public/js/doctype/Task.js",
    "CRM Deal": "public/js/doctype/CRM_Deal.js",
    "Project": "public/js/doctype/Project.js",
    "Issue": "public/js/doctype/Issue.js",
    "Delivery Note": "public/js/doctype/Delivery_Note.js",
    "Stock Entry": "public/js/doctype/Stock_Entry.js",
}

doctype_list_js = {
    # "Lead": "public/js/listview/Lead_listview.js",
    # "Opportunity": "public/js/listview/Opportunity_listview.js",
    "Customer": "public/js/listview/Customer_listview.js",
    "User": "public/js/listview/user_listview.js",
    "Calendar Events": "public/js/calendar.js",
    "Issue": "public/js/listview/issue_listview.js",
    # "Project": "public/js/listview/project_listview.js",
}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# "Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# "methods": "ivm.utils.jinja_methods",
# "filters": "ivm.utils.jinja_filters"
# }

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

# override_doctype_class = {
# "ToDo": "custom_app.overrides.CustomToDo"
# }
# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Communication": {
        "on_update": "ivm.api.creating_issue",
    },
    "Issue": {
        "on_update": "ivm.api.fetching_dates"
    },
    "Item": {
        "before_save": "ivm.warehouse.event_handlers.item.before_save"
    },
    "Wiki Document": {
        "on_update": "ivm.integrations.wiki.content_webhook.on_wiki_document_update",
    },
    "CRM Deal": {
        "on_update": "ivm.deployments.event_handlers.deal.on_update",
    },
    "Project": {
        "before_validate": "ivm.deployments.event_handlers.project.before_validate",
        "validate": "ivm.deployments.event_handlers.project.validate",
        "after_insert": "ivm.deployments.event_handlers.project.after_insert",
    },
}

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
}

# Testing
# -------

# before_tests = "ivm.install.before_tests"

# Overriding Methods
# ------------------------------
#
override_whitelisted_methods = {
    "frappe.desk.search.get_value": "ivm.machine_hardware_management.overrides.virtual_get_value.virtual_get_value"
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
