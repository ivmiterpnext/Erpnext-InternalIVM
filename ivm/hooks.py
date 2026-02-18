from . import __version__ as app_version

app_name = "ivm"
app_title = "IVM"
app_publisher = "korecent"
app_description = "IVM customizations"
app_email = "hello@korecent.com"
app_license = "MIT"

# Includes in <head>
# ------------------
fixtures = [
    "Workspace", "Dashboard", "Issue Type", "Campaign", "Sales Stage", "Case Reason", "Lead Source", "Translation", "Connectivity Type", "List View Settings", "Workflow Action Master", "Custom DocPerm",
    "Opportunity Type", "Workflow", "Property Setter", "Workflow State", "Industry Type", "Role"
]

# Add to apps screen (for v16 navigation)
add_to_apps_screen = [
    {
        "name": "ivm",
        "logo": "/assets/ivm/images/ivm-logo.png",
        "title": "IVM",
        "route": "/app/ivm",
    }
]

# include js, css files in header of desk.html
# app_include_css = "/assets/ivm/css/ivm.css"
app_include_js = ["/assets/ivm/js/workspace.js","/assets/ivm/js/awesome_bar.js"]

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
    "Lead": "public/js/doctype/Lead.js",
    "Opportunity": "public/js/doctype/Opportunity.js",
    "Customer": "public/js/doctype/Customer.js",
    "Deployment Location": "public/js/doctype/Deployment_location.js",
    "User": "public/js/doctype/user.js",
    "Task": "public/js/doctype/Task.js",
    "Project": "public/js/doctype/Project.js",
    "Issue": "public/js/doctype/Issue.js"
}

doctype_list_js = {
    "Lead": "public/js/listview/Lead_listview.js",
    "Opportunity": "public/js/listview/Opportunity_listview.js",
    "Customer": "public/js/listview/Customer_listview.js",
    "User": "public/js/listview/user_listview.js",
    "Calendar Events": "public/js/calendar.js",
    "Issue": "public/js/listview/issue_listview.js"
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

# Session Creation
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

after_migrate = [
    "ivm.ivm_integrations.hubspot.setup.create_custom_fields",
]

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
override_doctype_class = {
    "Project": "ivm.controllers.project.CustomProjectController"
}
# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
    "Communication": {
        "on_update": "ivm.api.creating_issue",
    },
    "Issue": {
        "on_update": "ivm.api.fetching_dates"
    # },
    # "Contact": {
    #     "after_insert": "ivm.contact_sync.sync_contact_to_mssql",
    #     "on_update": "ivm.contact_sync.update_contact_in_mssql",
    },
    "CRM Deal": {
        "on_update": "ivm.ivm_integrations.hubspot.deal_events.on_update",
    },
    "Custom Field": {
        "after_insert": "ivm.utils.auto_export.auto_export_custom_field",
        "on_update": "ivm.utils.auto_export.auto_export_custom_field",
        "on_trash": "ivm.utils.auto_export.auto_export_custom_field",
    },
    "Property Setter": {
        "after_insert": "ivm.utils.auto_export.auto_export_property_setter",
        "on_update": "ivm.utils.auto_export.auto_export_property_setter",
        "on_trash": "ivm.utils.auto_export.auto_export_property_setter",
    }
}

# Scheduled Tasks
# ---------------

scheduler_events = {
    "daily": [
        "ivm.client_management.doctype.address_link.address_link.sync",
        "ivm.client_management.doctype.client_link.client_link.sync",
        "ivm.client_management.location_link.location_link.sync",
    
        "ivm.machine_hardware_management.doctype.agreement_fee_type.agreement_fee_type.sync",
        "ivm.machine_hardware_management.doctype.board_link.board_link.sync",
        "ivm.machine_hardware_management.doctype.board_connection.board_connection.sync",
        "ivm.machine_hardware_management.doctype.board_firmware.board_firmware.sync",
        "ivm.machine_hardware_management.doctype.board_manufacturer.board_manufacturer.sync",
        "ivm.machine_hardware_management.doctype.board_type.board_type.sync",
        "ivm.machine_hardware_management.doctype.hardware_availability_type.hardware_availability_type.sync",
        "ivm.machine_hardware_management.doctype.hardware_connectivity_type.hardware_connectivity_type.sync",
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
# "all": [
# "ivm.tasks.all"
# ],
# "daily": [
# "ivm.tasks.daily"
# ],
# "hourly": [
# "ivm.tasks.hourly"
# ],
# "weekly": [
# "ivm.tasks.weekly"
# ],
# "monthly": [
# "ivm.tasks.monthly"
# ],
# }

# Testing
# -------

# before_tests = "ivm.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# "frappe.desk.doctype.event.event.get_events": "ivm.event.get_events"
# }
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
