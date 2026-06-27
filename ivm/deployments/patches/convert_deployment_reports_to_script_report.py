"""
Convert My Open Deployments and All open deployments dashboard from Report Builder
to Script Report so their Python scripts are executed at runtime.
"""

import frappe


def execute():
    for report_name in ("My Open Deployments", "All open deployments dashboard"):
        if frappe.db.exists("Report", report_name):
            frappe.db.set_value(
                "Report",
                report_name,
                {"report_type": "Script Report", "is_standard": "Yes", "module": "IVM"},
                update_modified=False,
            )
            print(f"  Converted report to Script Report: {report_name}")
