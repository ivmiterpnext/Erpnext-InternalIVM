"""iCorpClientLink.on_update: live (Customer form) assignments must not write back to the repo CSVs
on the review site; review-site decisions made without the flag still do."""

import random
from unittest.mock import MagicMock, patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

_WRITE_BACK = (
	"ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link._write_decisions_for_client"
)


def _make_customer(suffix: str) -> str:
	if not frappe.db.exists("Customer Group", "_Test Customer Group"):
		frappe.get_doc(
			{"doctype": "Customer Group", "customer_group_name": "_Test Customer Group", "is_group": 0}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": f"Test On Update {suffix} {frappe.generate_hash(length=8)}",
			"customer_type": "Company",
			"customer_group": "_Test Customer Group",
			"territory": "All Territories",
		}
	).insert(ignore_permissions=True)
	return doc.name


def _make_icorp_client_link() -> str:
	client_id = "".join(random.choices("0123456789", k=9))
	doc = frappe.get_doc(
		{
			"doctype": "iCorp Client Link",
			"icorp_client_id": client_id,
			"client_name": f"Client {client_id}",
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
	return doc.name


class TestOnUpdateLiveAssignment(ERPNextTestSuite):
	"""iCorpClientLink.on_update write-back gating on flags.live_assignment (review site)"""

	def _review_site(self):
		original = frappe.conf.get("customer_consolidation_review_site")
		frappe.conf.customer_consolidation_review_site = 1

		def _restore():
			if original is None:
				frappe.conf.pop("customer_consolidation_review_site", None)
			else:
				frappe.conf.customer_consolidation_review_site = original

		self.addCleanup(_restore)

	def _run_after_commit_immediately(self):
		# Tests roll back, so after_commit callbacks never fire; run the on_update write-back
		# inline instead. Only that callback (qualname contains "on_update") is executed; Frappe's
		# own after_commit hooks (realtime flush etc.) are ignored, since running them inline
		# would clear state mid-save.
		def _run_on_update_callbacks_only(fn):
			if "on_update" in getattr(fn, "__qualname__", ""):
				fn()

		fake_after_commit = MagicMock()
		fake_after_commit.add.side_effect = _run_on_update_callbacks_only
		patcher = patch.object(frappe.db, "after_commit", fake_after_commit)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_live_assignment_does_not_write_back(self):
		self._review_site()
		self._run_after_commit_immediately()
		name = _make_icorp_client_link()
		customer = _make_customer("Live")

		with patch(_WRITE_BACK) as mock_write:
			doc = frappe.get_doc("iCorp Client Link", name)
			doc.customer = customer
			doc.assignment_source = "Customer form"
			doc.flags.live_assignment = True
			doc.save(ignore_permissions=True)

		mock_write.assert_not_called()

	def test_review_decision_without_flag_still_writes_back(self):
		self._review_site()
		self._run_after_commit_immediately()
		name = _make_icorp_client_link()
		customer = _make_customer("Review")

		with patch(_WRITE_BACK) as mock_write:
			doc = frappe.get_doc("iCorp Client Link", name)
			doc.customer = customer
			doc.assignment_source = "Manual decision"
			doc.save(ignore_permissions=True)

		mock_write.assert_called_once()
		args = mock_write.call_args.args
		self.assertEqual(args[0], name)
		self.assertEqual(args[1], customer)
