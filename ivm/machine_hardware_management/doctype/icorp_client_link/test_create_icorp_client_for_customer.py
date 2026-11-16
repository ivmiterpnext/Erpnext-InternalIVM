"""Tests for create_icorp_client_for_customer (Customer form -> new iCorp client).

All iCorp traffic is mocked at the provisioning module (icorp_api_post) and the
iCorp Client Link module (icorp_api_get). No live iCorp calls.
"""

import random
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link import (
	create_icorp_client_for_customer,
)

_ICORP_POST = "ivm.integrations.icorp.provisioning.icorp_api_post"
_ICORP_GET = "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_api_get"
_LOG_ICORP_ERROR_PROVISIONING = "ivm.integrations.icorp.provisioning.log_icorp_error"
_LOG_ICORP_ERROR_LINK = (
	"ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.log_icorp_error"
)
_ICORP_NON_JSON_ERROR = {
	"error": "Invalid JSON response",
	"status_code": 400,
	"text": "Must have a least 1 contact phone number.",
}


def _rand_id() -> str:
	return str(random.randint(200_000_000, 299_999_999))


def _make_low_privilege_user() -> str:
	email = f"test_create_icorp_{frappe.generate_hash(length=8)}@example.com"
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "Low Privilege",
			"send_welcome_email": 0,
			"roles": [{"role": "Projects User"}],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_customer(suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "_Test Customer Group", "is_group": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Create Client {suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_contact(first_name: str, customer: str | None = None, phone: str | None = "5550100100") -> str:
	links = [{"link_doctype": "Customer", "link_name": customer}] if customer else []
	doc = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": f"{first_name} {frappe.generate_hash(length=6)}",
			"email_ids": [{"email_id": f"{frappe.generate_hash(length=6)}@example.com", "is_primary": 1}],
			"phone_nos": [{"phone": phone, "is_primary_phone": 1}] if phone else [],
			"links": links,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_partner_link(suffix: str) -> str:
	client_id = _rand_id()
	frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": client_id,
			"client_name": f"Partner {suffix}",
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
	return client_id


class TestCreateIcorpClientForCustomer(ERPNextTestSuite):
	"""Customer form -> iCorp contact + client creation, with iCorp fully mocked."""

	def setUp(self):
		super().setUp()
		self.mock_post = patch(_ICORP_POST).start()
		self.mock_get = patch(_ICORP_GET).start()
		# tabError Log is MyISAM, so Error Logs written here would survive teardown; stub the
		# logger. The real persistence path is covered by TestIcorpErrorLogPersistence.
		patch(_LOG_ICORP_ERROR_PROVISIONING).start()
		patch(_LOG_ICORP_ERROR_LINK).start()
		self.addCleanup(patch.stopall)

	def _post_side_effect(self, contact_response, client_response):
		def side_effect(endpoint, data, headers=None):
			if endpoint == "Contact":
				return contact_response(data) if callable(contact_response) else contact_response
			if endpoint == "Client":
				return client_response(data) if callable(client_response) else client_response
			raise AssertionError(f"unexpected iCorp endpoint {endpoint}")

		return side_effect

	def _ok_contact(self, contact_id=5551):
		return {"data": {"id": contact_id}}

	def test_success_creates_contact_and_client_linked_to_customer(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("Ok", customer)
		client_id = _rand_id()
		self.mock_post.side_effect = self._post_side_effect(
			self._ok_contact(5551), {"data": {"id": int(client_id)}}
		)

		result = create_icorp_client_for_customer(customer, "Acme Client", contact)

		self.assertEqual(result, {"client_id": client_id, "customer": customer})
		link = frappe.db.get_value(
			"iCorp Client Link",
			client_id,
			["customer", "assignment_source", "parent_client", "is_active", "client_name"],
			as_dict=True,
		)
		self.assertEqual(link.customer, customer)
		self.assertEqual(link.assignment_source, "Customer form")
		self.assertFalse(link.parent_client)
		self.assertEqual(link.is_active, 1)
		self.assertEqual(link.client_name, "Acme Client")

		endpoints = [c.args[0] for c in self.mock_post.call_args_list]
		self.assertEqual(endpoints, ["Contact", "Client"])
		contact_payload = self.mock_post.call_args_list[0].args[1]
		self.assertTrue(contact_payload["email_address"].endswith("@example.com"))
		client_payload = self.mock_post.call_args_list[1].args[1]
		self.assertEqual(client_payload["name"], "Acme Client")
		self.assertEqual(client_payload["primary_contact_id"], 5551)
		self.assertTrue(client_payload["is_active"])
		self.assertFalse(client_payload["is_enhanced_client"])
		self.assertFalse(client_payload["using_enhanced_assignments"])
		self.assertEqual(client_payload["restriction_priority_type_id"], 2)
		self.assertEqual(client_payload["check_frequency_type_code"], "M")
		self.assertEqual(client_payload["fee_rate_id"], 1)
		self.assertNotIn("partner_client_id", client_payload)
		self.mock_get.assert_not_called()

	def test_partner_sets_parent_client_and_payload_key(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("Partner", customer)
		partner = _make_partner_link(frappe.generate_hash(length=4))
		client_id = _rand_id()
		self.mock_post.side_effect = self._post_side_effect(
			self._ok_contact(), {"data": {"id": int(client_id)}}
		)

		create_icorp_client_for_customer(customer, "Managed Client", contact, partner_client_id=partner)

		client_payload = self.mock_post.call_args_list[1].args[1]
		self.assertEqual(client_payload["partner_client_id"], int(partner))
		self.assertEqual(frappe.db.get_value("iCorp Client Link", client_id, "parent_client"), partner)
		self.assertEqual(frappe.db.get_value("iCorp Client Link", client_id, "customer"), customer)

	def test_unknown_partner_rejected_before_any_icorp_call(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("NoPartner", customer)

		with self.assertRaises(frappe.ValidationError):
			create_icorp_client_for_customer(customer, "X", contact, partner_client_id="999999999")
		self.mock_post.assert_not_called()

	def test_contact_not_linked_to_customer_rejected(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("Unlinked")

		with self.assertRaises(frappe.ValidationError):
			create_icorp_client_for_customer(customer, "Acme", contact)
		self.mock_post.assert_not_called()

	def test_contact_linked_to_other_customer_rejected(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		other = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("OtherCust", other)

		with self.assertRaises(frappe.ValidationError):
			create_icorp_client_for_customer(customer, "Acme", contact)
		self.mock_post.assert_not_called()

	def test_blank_client_name_rejected(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("Blank", customer)

		with self.assertRaises(frappe.ValidationError):
			create_icorp_client_for_customer(customer, "   ", contact)
		self.mock_post.assert_not_called()

	def test_contact_creation_error_response_throws_and_creates_no_client(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("ContactErr", customer)
		self.mock_post.side_effect = self._post_side_effect({"error": "bad contact"}, None)

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_icorp_client_for_customer(customer, "Acme", contact)

		self.assertIn("no client was created", str(ctx.exception))
		self.assertIn("bad contact", str(ctx.exception))
		self.assertEqual([c.args[0] for c in self.mock_post.call_args_list], ["Contact"])
		self.assertEqual(frappe.db.count("iCorp Client Link", {"customer": customer}), 0)

	def test_contact_created_but_client_error_names_contact_id(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("ClientErr", customer)
		self.mock_post.side_effect = self._post_side_effect(self._ok_contact(7777), {"error": "boom"})

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_icorp_client_for_customer(customer, "Acme", contact)

		self.assertIn("7777", str(ctx.exception))
		self.assertIn("was created", str(ctx.exception))
		self.assertEqual(frappe.db.count("iCorp Client Link", {"customer": customer}), 0)

	def test_contact_created_but_client_exception_names_contact_id(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("ClientExc", customer)

		def client_raises(data):
			raise RuntimeError("network down")

		self.mock_post.side_effect = self._post_side_effect(self._ok_contact(8888), client_raises)

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_icorp_client_for_customer(customer, "Acme", contact)

		self.assertIn("8888", str(ctx.exception))
		self.assertEqual(frappe.db.count("iCorp Client Link", {"customer": customer}), 0)

	def test_role_check_rejects_other_roles(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("Role", customer)
		low_privilege_user = _make_low_privilege_user()
		original_user = frappe.session.user
		frappe.set_user(low_privilege_user)
		try:
			with self.assertRaises(frappe.PermissionError):
				create_icorp_client_for_customer(customer, "Acme", contact)
		finally:
			frappe.set_user(original_user)
		self.mock_post.assert_not_called()

	def test_contact_without_phone_throws_before_any_icorp_call(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("NoPhone", customer, phone=None)

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_icorp_client_for_customer(customer, "Acme", contact)

		self.assertIn(f"Add a phone number to {contact} first.", str(ctx.exception))
		self.mock_post.assert_not_called()
		self.assertEqual(frappe.db.count("iCorp Client Link", {"customer": customer}), 0)

	def test_contact_non_json_error_throws_icorp_text(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("NonJsonContact", customer)
		self.mock_post.side_effect = self._post_side_effect(dict(_ICORP_NON_JSON_ERROR), None)

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_icorp_client_for_customer(customer, "Acme", contact)

		message = str(ctx.exception)
		self.assertIn("Must have a least 1 contact phone number.", message)
		self.assertIn("(HTTP 400)", message)
		self.assertNotIn("Invalid JSON response", message)
		self.assertEqual([c.args[0] for c in self.mock_post.call_args_list], ["Contact"])

	def test_client_non_json_error_throws_icorp_text(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("NonJsonClient", customer)
		self.mock_post.side_effect = self._post_side_effect(
			self._ok_contact(9999), dict(_ICORP_NON_JSON_ERROR)
		)

		with self.assertRaises(frappe.ValidationError) as ctx:
			create_icorp_client_for_customer(customer, "Acme", contact)

		message = str(ctx.exception)
		self.assertIn("9999", message)
		self.assertIn("Must have a least 1 contact phone number.", message)
		self.assertEqual(frappe.db.count("iCorp Client Link", {"customer": customer}), 0)


class TestIcorpErrorLogPersistence(ERPNextTestSuite):
	"""The provisioning Error Log must survive the rollback that follows frappe.throw.

	Uses the real _persist_error_log (no patch). Calls frappe.db.rollback() the way the
	request handler does after an exception, then checks the row exists.
	"""

	def setUp(self):
		super().setUp()
		self.mock_post = patch(_ICORP_POST).start()
		self.addCleanup(patch.stopall)

	def test_contact_error_log_survives_throw_and_rollback(self):
		customer = _make_customer(frappe.generate_hash(length=6))
		contact = _make_contact("Persist", customer)
		self.mock_post.return_value = dict(_ICORP_NON_JSON_ERROR)

		with self.assertRaises(frappe.ValidationError):
			create_icorp_client_for_customer(customer, "Acme", contact)
		frappe.db.rollback()  # request handler rollback after the exception

		filters = {"method": "iCorp: failed to create contact", "error": ["like", f"%{contact}%"]}
		logs = frappe.get_all("Error Log", filters=filters, fields=["name", "error"])
		try:
			self.assertEqual(len(logs), 1)
			self.assertIn("Must have a least 1 contact phone number.", logs[0].error)
		finally:
			# Committed by design; remove so test.local stays clean.
			frappe.db.delete("Error Log", {"name": ["in", [row.name for row in logs]]})
			frappe.db.commit()
