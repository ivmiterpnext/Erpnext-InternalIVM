"""Integration tests for ivm.client_portal.event_handlers.user"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.event_handlers.user import enforce_portal_user_roles

PORTAL_ROLE = "Service Portal User"


class TestEnforcePortalUserRoles(ERPNextTestSuite):
	"""enforce_portal_user_roles"""

	def _make_user_doc(self, roles):
		"""Build an in-memory User document with the given role names.

		Does NOT insert — the function under test only reads doc.roles
		in-memory and queries the Role table (which exists in the DB).
		"""
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": f"portaltest-{frappe.generate_hash(length=6)}@test.local",
				"first_name": "Portal Test",
				"roles": [{"role": r} for r in roles],
			}
		)

	def test_noop_when_no_portal_role(self):
		user_doc = self._make_user_doc(["System Manager"])
		original_roles = {r.role for r in user_doc.roles}

		enforce_portal_user_roles(user_doc, "before_validate")

		self.assertEqual({r.role for r in user_doc.roles}, original_roles)

	def test_strips_desk_access_role(self):
		user_doc = self._make_user_doc([PORTAL_ROLE, "System Manager"])

		enforce_portal_user_roles(user_doc, "before_validate")

		role_names = {r.role for r in user_doc.roles}
		self.assertNotIn("System Manager", role_names)
		self.assertIn(PORTAL_ROLE, role_names)

	def test_strips_multiple_desk_roles(self):
		desk_roles = frappe.get_all(
			"Role",
			filters={"desk_access": 1},
			pluck="name",
			limit=3,
		)
		if len(desk_roles) < 2:
			self.skipTest("Need at least 2 desk-access roles for this test")

		user_doc = self._make_user_doc([PORTAL_ROLE, *desk_roles])

		enforce_portal_user_roles(user_doc, "before_validate")

		role_names = {r.role for r in user_doc.roles}
		for dr in desk_roles:
			self.assertNotIn(dr, role_names)
		self.assertIn(PORTAL_ROLE, role_names)

	def test_logs_warning_when_roles_stripped(self):
		user_doc = self._make_user_doc([PORTAL_ROLE, "System Manager"])

		with patch("frappe.logger") as mock_logger:
			enforce_portal_user_roles(user_doc, "before_validate")
			mock_logger.return_value.warning.assert_called_once()

	def test_no_warning_when_nothing_stripped(self):
		user_doc = self._make_user_doc([PORTAL_ROLE])

		with patch("frappe.logger") as mock_logger:
			enforce_portal_user_roles(user_doc, "before_validate")
			mock_logger.return_value.warning.assert_not_called()
