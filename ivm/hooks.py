app_name = "ivm"
app_title = "IVM"
app_publisher = "IVM"
app_description = "IVM Integration App"
app_email = "itsupport@ivminc.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "ivm",
# 		"logo": "/assets/ivm/logo.png",
# 		"title": "IVM",
# 		"route": "/ivm",
# 		"has_permission": "ivm.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/ivm/css/ivm.css"
# app_include_js = "/assets/ivm/js/ivm.js"

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
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "ivm/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "ivm.utils.jinja_methods",
# 	"filters": "ivm.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "ivm.install.before_install"
# after_install = "ivm.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "ivm.uninstall.before_uninstall"
# after_uninstall = "ivm.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "ivm.utils.before_app_install"
# after_app_install = "ivm.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "ivm.utils.before_app_uninstall"
# after_app_uninstall = "ivm.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "ivm.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

doc_events = {
    # "Communication": {
    #     "on_update": "ivm.api.creating_issue",
    # },
    # "Issue": {
    #     "on_update": "ivm.api.fetching_dates"
    # },
    # "Contact": {
    #     "after_insert": "ivm.contact_sync.sync_contact_to_mssql",
    #     "on_update": "ivm.contact_sync.update_contact_in_mssql",
    #},
    "Custom Field": {
        "after_insert": "ivm.ivm.utils.auto_export.auto_export_custom_field",
        "on_update": "ivm.ivm.utils.auto_export.auto_export_custom_field",
        "on_trash": "ivm.ivm.utils.auto_export.auto_export_custom_field",
    },
    "Property Setter": {
        "after_insert": "ivm.ivm.utils.auto_export.auto_export_property_setter",
        "on_update": "ivm.ivm.utils.auto_export.auto_export_property_setter",
        "on_trash": "ivm.ivm.utils.auto_export.auto_export_property_setter",
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"ivm.tasks.all"
# 	],
# 	"daily": [
# 		"ivm.tasks.daily"
# 	],
# 	"hourly": [
# 		"ivm.tasks.hourly"
# 	],
# 	"weekly": [
# 		"ivm.tasks.weekly"
# 	],
# 	"monthly": [
# 		"ivm.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "ivm.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "ivm.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "ivm.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "ivm.task.get_dashboard_data"
# }

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
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"ivm.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

