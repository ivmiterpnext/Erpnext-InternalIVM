"""Guardrail tests for the "New Build Request" notification and its related fixes.

Covers the 2026-11 incident where "New Build Request" reused the legacy
field number_1_task_sent as its set_property_after_alert flag, which
re-triggered the dead "Send Machine Numbers to ICS 1" Value Change
notification (AttributeError on the dropped created_by column). Also
guards the legacy ICS notifications being disabled, the Wrap Ready
Subject script no longer overwriting subject, the retired Prose ToDo
Task script being disabled, and the Shipping Address requirement on
build request generation.
"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.warehouse.services.warehouse_request import create_build_requests_from_detail_rows

NEW_BUILD_REQUEST = "New Build Request"
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
PROSE_TODO_SCRIPT = "Prose ToDo Task for Deployment"
WRAP_READY_SCRIPT = "Wrap Ready Subject"
COMPANY = "_Test Company"


class TestBuildRequestNotifications(ERPNextTestSuite):
	def test_new_build_request_notification_has_no_value_changed_trigger(self):
		notification = frappe.get_doc("Notification", NEW_BUILD_REQUEST)
		self.assertFalse(notification.value_changed)
		self.assertFalse(notification.set_property_after_alert)

	def test_legacy_ics_notifications_are_disabled(self):
		for name in LEGACY_ICS_NOTIFICATIONS:
			with self.subTest(notification=name):
				notification = frappe.get_doc("Notification", name)
				self.assertEqual(notification.enabled, 0)

	def test_prose_todo_task_script_is_disabled(self):
		script = frappe.get_doc("Server Script", PROSE_TODO_SCRIPT)
		self.assertEqual(script.disabled, 1)

	def test_wrap_ready_subject_script_has_no_build_block(self):
		script = frappe.get_doc("Server Script", WRAP_READY_SCRIPT)
		self.assertNotIn("Build", script.script)
		self.assertIn("Wrap Ready", script.script)

	def test_generate_build_requests_requires_shipping_address(self):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": frappe.generate_hash(length=10),
				"customer_group": "_Test Customer Group",
				"territory": "_Test Territory",
			}
		)
		customer.insert(ignore_permissions=True)

		client = frappe.get_doc(
			{
				"doctype": "iCorp Client Link",
				"icorp_client_id": "100030",
				"client_name": "Test Client 100030",
				"customer": customer.name,
				"is_active": 1,
			}
		)
		client.insert(ignore_permissions=True)
		self.addCleanup(
			lambda: frappe.delete_doc("iCorp Client Link", client.name, force=True, ignore_permissions=True)
		)

		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": f"Test Project - {frappe.generate_hash(length=6)}",
				"project_type": "Deployment",
				"customer": customer.name,
				"icorp_client_id": client.name,
				"company": COMPANY,
			}
		)
		project.insert(ignore_permissions=True)
		project.append(
			"custom_deployment_smartstation_details",
			{"machine_name": f"MACH-{frappe.generate_hash(length=6)}"},
		)
		project.save(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_build_requests_from_detail_rows(project.name, "custom_deployment_smartstation_details")
		self.assertIn("Shipping Address", str(ctx.exception))
