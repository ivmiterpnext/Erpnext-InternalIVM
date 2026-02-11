app_name = "Machine Hardware Management"
app_title = "Machine Hardware Management"
app_publisher = "Dev"
app_description = "ICORP Machine Hardware Management Integration"
app_email = "lhammond@ivminc.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "machine_hardware_management",
# 		"logo": "/assets/machine_hardware_management/logo.png",
# 		"title": "Machine Hardware Management",
# 		"route": "/machine_hardware_management",
# 		"has_permission": "machine_hardware_management.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/machine_hardware_management/css/machine_hardware_management.css"
# app_include_js = "/assets/machine_hardware_management/js/machine_hardware_management.js"

# include js, css files in header of web template
# web_include_css = "/assets/machine_hardware_management/css/machine_hardware_management.css"
# web_include_js = "/assets/machine_hardware_management/js/machine_hardware_management.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "machine_hardware_management/public/scss/website"

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
# app_include_icons = "machine_hardware_management/public/icons.svg"

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
# 	"methods": "machine_hardware_management.utils.jinja_methods",
# 	"filters": "machine_hardware_management.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "machine_hardware_management.install.before_install"
# after_install = "machine_hardware_management.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "machine_hardware_management.uninstall.before_uninstall"
# after_uninstall = "machine_hardware_management.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "machine_hardware_management.utils.before_app_install"
# after_app_install = "machine_hardware_management.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "machine_hardware_management.utils.before_app_uninstall"
# after_app_uninstall = "machine_hardware_management.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "machine_hardware_management.notifications.get_notification_config"

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

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "ivm.machine_hardware_management.doctype.address_link.address_link.sync",
        "ivm.machine_hardware_management.doctype.agreement_fee_type.agreement_fee_type.sync",
        "ivm.machine_hardware_management.doctype.board_link.board_link.sync",
        "ivm.machine_hardware_management.doctype.board_connection.board_connection.sync",
        "ivm.machine_hardware_management.doctype.board_firmware.board_firmware.sync",
        "ivm.machine_hardware_management.doctype.board_manufacturer.board_manufacturer.sync",
        "ivm.machine_hardware_management.doctype.board_type.board_type.sync",
        "ivm.machine_hardware_management.doctype.client_link.client_link.sync",
        "ivm.machine_hardware_management.doctype.hardware_availability_type.hardware_availability_type.sync",
        "ivm.machine_hardware_management.doctype.hardware_connectivity_type.hardware_connectivity_type.sync",
        "ivm.machine_hardware_management.doctype.location_link.location_link.sync",
        "ivm.machine_hardware_management.doctype.machine_activity_log_type.machine_activity_log_type.sync",
        "ivm.machine_hardware_management.doctype.machine_authorization_type.machine_authorization_type.sync",
        "ivm.machine_hardware_management.doctype.machine_contract_length_type.machine_contract_length_type.sync",
        "ivm.machine_hardware_management.doctype.machine_link.machine_link.sync",
        "ivm.machine_hardware_management.doctype.machine_purpose.machine_purpose.sync",
        "ivm.machine_hardware_management.doctype.machine_status_type.machine_status_type.sync",
        "ivm.machine_hardware_management.doctype.machine_type.machine_type.sync",
        "ivm.machine_hardware_management.doctype.push_message_type.push_message_type.sync",
        "ivm.machine_hardware_management.doctype.smart_screen_configuration.smart_screen_configuration.sync",
        "ivm.machine_hardware_management.doctype.smart_screen_group.smart_screen_group.sync",
        "ivm.machine_hardware_management.doctype.vendor_link.vendor_link.sync"
    ],
}

# scheduler_events = {
# 	"all": [
# 		"machine_hardware_management.tasks.all"
# 	],
# 	"daily": [
# 		"machine_hardware_management.tasks.daily"
# 	],
# 	"hourly": [
# 		"machine_hardware_management.tasks.hourly"
# 	],
# 	"weekly": [
# 		"machine_hardware_management.tasks.weekly"
# 	],
# 	"monthly": [
# 		"machine_hardware_management.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "machine_hardware_management.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "machine_hardware_management.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "machine_hardware_management.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["machine_hardware_management.utils.before_request"]
# after_request = ["machine_hardware_management.utils.after_request"]

# Job Events
# ----------
# before_job = ["machine_hardware_management.utils.before_job"]
# after_job = ["machine_hardware_management.utils.after_job"]

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
# 	"machine_hardware_management.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
