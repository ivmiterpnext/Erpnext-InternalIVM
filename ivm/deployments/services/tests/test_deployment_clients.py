"""Tests for ivm.deployments.services.deployment_clients"""

import random
import string

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.deployment_clients import (
	derive_partner,
	get_deployable_clients,
	parse_project_client_ids,
)


def _rand_id() -> str:
	"""Random 6-digit numeric string, safe for iCorp Client Link's field:icorp_client_id autoname."""
	return "".join(random.choices(string.digits, k=6))


def _make_customer(name_suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{
				"doctype": "Customer Group",
				"customer_group_name": "_Test Customer Group",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test Customer {name_suffix}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
		}
	)
	customer.insert(ignore_permissions=True)
	return customer.name


def _make_client(icorp_client_id, customer=None, parent_client=None, is_active=1, client_name=None):
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": icorp_client_id,
			"client_name": client_name or f"Test Client {icorp_client_id}",
			"customer": customer,
			"parent_client": parent_client,
			"is_active": is_active,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestGetDeployableClients(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self._cleanup_names = []

	def tearDown(self):
		for doctype, name in reversed(self._cleanup_names):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		super().tearDown()

	def _track(self, doctype, name):
		self._cleanup_names.append((doctype, name))
		return name

	def test_own_clients_only(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"Own {uid}"))
		client = self._track("iCorp Client Link", _make_client(_rand_id(), customer=customer))

		result = get_deployable_clients(customer)

		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["name"], client)
		self.assertEqual(result[0]["group"], "own")
		self.assertIsNone(result[0]["partner_customer"])

	def test_multiple_own_clients_sorted_by_name(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"Multi {uid}"))
		self._track(
			"iCorp Client Link", _make_client(_rand_id(), customer=customer, client_name="Zeta Client")
		)
		self._track(
			"iCorp Client Link", _make_client(_rand_id(), customer=customer, client_name="Alpha Client")
		)

		result = get_deployable_clients(customer)

		self.assertEqual(len(result), 2)
		self.assertEqual([r["client_name"] for r in result], ["Alpha Client", "Zeta Client"])
		self.assertTrue(all(r["group"] == "own" for r in result))

	def test_managed_client_shows_end_customer(self):
		uid = frappe.generate_hash(length=6)
		partner_customer = self._track("Customer", _make_customer(f"Partner {uid}"))
		end_customer = self._track("Customer", _make_customer(f"End {uid}"))
		parent = self._track("iCorp Client Link", _make_client(_rand_id(), customer=partner_customer))
		managed = self._track(
			"iCorp Client Link",
			_make_client(_rand_id(), customer=end_customer, parent_client=parent),
		)

		result = get_deployable_clients(partner_customer)

		# The partner's own client (parent) AND the managed client both come back --
		# a partner Customer typically also has its own client for itself.
		by_name = {r["name"]: r for r in result}
		self.assertIn(parent, by_name)
		self.assertEqual(by_name[parent]["group"], "own")

		self.assertIn(managed, by_name)
		self.assertEqual(by_name[managed]["group"], "managed")
		self.assertEqual(by_name[managed]["customer"], end_customer)
		self.assertEqual(by_name[managed]["partner_customer"], partner_customer)

	def test_sibling_clients_not_treated_as_managed(self):
		"""Parent and child both assigned to the SAME customer -> no managed row for that customer,
		and the child still shows up under its own customer as 'own', not 'managed'."""
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"Sibling {uid}"))
		parent = self._track("iCorp Client Link", _make_client(_rand_id(), customer=customer))
		child = self._track(
			"iCorp Client Link", _make_client(_rand_id(), customer=customer, parent_client=parent)
		)

		result = get_deployable_clients(customer)

		names = {r["name"]: r for r in result}
		self.assertEqual(len(result), 2)
		self.assertEqual(names[parent]["group"], "own")
		self.assertEqual(names[child]["group"], "own")

	def test_inactive_clients_excluded(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"Inactive {uid}"))
		self._track("iCorp Client Link", _make_client(_rand_id(), customer=customer, is_active=0))

		result = get_deployable_clients(customer)

		self.assertEqual(result, [])

	def test_no_clients_returns_empty_list(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"None {uid}"))

		result = get_deployable_clients(customer)

		self.assertEqual(result, [])

	def test_blank_customer_returns_empty_list(self):
		self.assertEqual(get_deployable_clients(""), [])
		self.assertEqual(get_deployable_clients(None), [])


class TestDerivePartner(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self._cleanup_names = []

	def tearDown(self):
		for doctype, name in reversed(self._cleanup_names):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		super().tearDown()

	def _track(self, doctype, name):
		self._cleanup_names.append((doctype, name))
		return name

	def test_no_parent_client_returns_none(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"NoParent {uid}"))
		client = self._track("iCorp Client Link", _make_client(_rand_id(), customer=customer))

		self.assertIsNone(derive_partner(client))

	def test_parent_same_customer_returns_none(self):
		uid = frappe.generate_hash(length=6)
		customer = self._track("Customer", _make_customer(f"SameCust {uid}"))
		parent = self._track("iCorp Client Link", _make_client(_rand_id(), customer=customer))
		child = self._track(
			"iCorp Client Link", _make_client(_rand_id(), customer=customer, parent_client=parent)
		)

		self.assertIsNone(derive_partner(child))

	def test_parent_different_customer_returns_parent_customer(self):
		uid = frappe.generate_hash(length=6)
		partner_customer = self._track("Customer", _make_customer(f"Partner2 {uid}"))
		end_customer = self._track("Customer", _make_customer(f"End2 {uid}"))
		parent = self._track("iCorp Client Link", _make_client(_rand_id(), customer=partner_customer))
		child = self._track(
			"iCorp Client Link",
			_make_client(_rand_id(), customer=end_customer, parent_client=parent),
		)

		self.assertEqual(derive_partner(child), partner_customer)

	def test_blank_client_id_returns_none(self):
		self.assertIsNone(derive_partner(""))
		self.assertIsNone(derive_partner(None))

	def test_derive_partner_client_matches_derive_partner_cases(self):
		uid = frappe.generate_hash(length=6)
		partner_customer = self._track("Customer", _make_customer(f"PartnerClient {uid}"))
		end_customer = self._track("Customer", _make_customer(f"EndClient {uid}"))
		sibling_customer = self._track("Customer", _make_customer(f"SiblingClient {uid}"))

		from ivm.deployments.services.deployment_clients import derive_partner_client

		no_parent = self._track("iCorp Client Link", _make_client(_rand_id(), customer=end_customer))
		self.assertIsNone(derive_partner_client(no_parent))

		same_customer_parent = self._track(
			"iCorp Client Link", _make_client(_rand_id(), customer=sibling_customer)
		)
		same_customer_child = self._track(
			"iCorp Client Link",
			_make_client(_rand_id(), customer=sibling_customer, parent_client=same_customer_parent),
		)
		self.assertIsNone(derive_partner_client(same_customer_child))

		real_partner_parent = self._track(
			"iCorp Client Link", _make_client(_rand_id(), customer=partner_customer)
		)
		managed_child = self._track(
			"iCorp Client Link",
			_make_client(_rand_id(), customer=end_customer, parent_client=real_partner_parent),
		)
		self.assertEqual(derive_partner_client(managed_child), real_partner_parent)

	def test_derive_partner_client_blank_input_returns_none(self):
		from ivm.deployments.services.deployment_clients import derive_partner_client

		self.assertIsNone(derive_partner_client(""))
		self.assertIsNone(derive_partner_client(None))


class TestParseProjectClientIds(ERPNextTestSuite):
	def test_empty_and_none_and_whitespace(self):
		for value in ("", None, "   "):
			result = parse_project_client_ids(value)
			self.assertEqual(result["status"], "empty")
			self.assertIsNone(result["primary"])

	def test_single_id(self):
		result = parse_project_client_ids("1328")
		self.assertEqual(result, {"primary": "1328", "others": [], "master": None, "status": "single"})

	def test_comma_separated_multi(self):
		result = parse_project_client_ids("1328, 1334")
		self.assertEqual(result, {"primary": "1328", "others": ["1334"], "master": None, "status": "multi"})

	def test_slash_separated_multi(self):
		result = parse_project_client_ids("1328/1334")
		self.assertEqual(result, {"primary": "1328", "others": ["1334"], "master": None, "status": "multi"})

	def test_master_suffix_with_colon(self):
		result = parse_project_client_ids("1334 (Master: 1011)")
		self.assertEqual(
			result, {"primary": "1334", "others": [], "master": "1011", "status": "master_suffix"}
		)

	def test_master_suffix_without_colon(self):
		result = parse_project_client_ids("1762 (Master 1756)")
		self.assertEqual(
			result, {"primary": "1762", "others": [], "master": "1756", "status": "master_suffix"}
		)

	def test_slash_multi_with_master_suffix(self):
		result = parse_project_client_ids("1629/1636 (Master: 1245)")
		self.assertEqual(
			result,
			{"primary": "1629", "others": ["1636"], "master": "1245", "status": "multi_master_suffix"},
		)

	def test_junk_input_is_malformed(self):
		result = parse_project_client_ids("abc")
		self.assertEqual(result["status"], "malformed")
		self.assertIsNone(result["primary"])
