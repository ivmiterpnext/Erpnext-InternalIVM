"""
Disable the 11 legacy ICS Notifications on Warehouse Request.

Frappe's fixture import preserves the DB value of Notification.enabled
(frappe/modules/import_file.py ignore_values), so setting "enabled": 0 in
ivm/fixtures/notification.json never reaches an existing site. This patch
applies the disable explicitly on every environment.

All 11 are superseded by ivm.warehouse.services.warehouse_request.send_equipment_info_to_ics().
It is safe to run repeatedly (idempotent).
"""

import frappe

LEGACY_ICS_NOTIFICATIONS = [
	"Send Machine Numbers to ICS 1",
	"Equipment Information Notification 2",
	"Equipment Information 3",
	"Equipment Information 4",
	"Equipment Information 5",
	"Equipment Information 6",
	"Equipment Information 7",
	"Equipment Information 8",
	"Equipment Information 9",
	"Equipment Information 10",
	"Equipment Information ALL",
]


def execute():
	for name in LEGACY_ICS_NOTIFICATIONS:
		if not frappe.db.exists("Notification", name):
			print(f"  Notification {name} does not exist — skipping")
			continue
		frappe.db.set_value("Notification", name, "enabled", 0, update_modified=False)
		print(f"  Disabled Notification {name}")
