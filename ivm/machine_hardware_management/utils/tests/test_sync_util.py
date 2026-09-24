from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestSyncDoctypeFromApi(FrappeTestCase):
	"""Test sync_doctype_from_api function from ivm.machine_hardware_management.utils.sync_util"""

	def setUp(self):
		from ivm.machine_hardware_management.utils.sync_util import sync_doctype_from_api

		self.sync_doctype_from_api = sync_doctype_from_api

	# ===== api_type routing =====

	@patch("ivm.integrations.icorp.icorp_api_get")
	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.commit")
	def test_api_type_icorp_calls_icorp_api_get(self, mock_commit, mock_get_all, mock_headwind, mock_icorp):
		"""api_type='icorp' calls icorp_api_get, not headwind_api_request"""
		mock_icorp.return_value = {"data": []}
		mock_get_all.return_value = []

		result = self.sync_doctype_from_api("TestDoc", "icorp", "/endpoint", "name", ["field1"])

		mock_icorp.assert_called_once_with("/endpoint")
		mock_headwind.assert_not_called()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.icorp.icorp_api_get")
	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.commit")
	def test_api_type_headwind_calls_headwind_api_request(
		self, mock_commit, mock_get_all, mock_headwind, mock_icorp
	):
		"""api_type='headwind' calls headwind_api_request, not icorp_api_get"""
		mock_headwind.return_value = {"data": []}
		mock_get_all.return_value = []

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1"])

		mock_headwind.assert_called_once_with("GET", "/endpoint")
		mock_icorp.assert_not_called()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.icorp.icorp_api_get")
	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.commit")
	@patch("frappe.logger")
	def test_api_type_unknown_returns_error_immediately(
		self, mock_logger, mock_commit, mock_get_all, mock_headwind, mock_icorp
	):
		"""api_type='bogus' logs error, returns error string, does NOT call get_all or sync"""
		mock_logger_instance = MagicMock()
		mock_logger.return_value = mock_logger_instance

		result = self.sync_doctype_from_api("TestDoc", "bogus", "/endpoint", "name", ["field1"])

		self.assertEqual(result, "Unknown api_type: bogus")
		mock_logger_instance.error.assert_called_once()
		mock_get_all.assert_not_called()
		mock_headwind.assert_not_called()
		mock_icorp.assert_not_called()
		mock_commit.assert_not_called()

	# ===== existing record path (update) =====

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.set_value")
	@patch("frappe.db.commit")
	def test_existing_record_with_field_changes_calls_set_value(
		self, mock_commit, mock_set_value, mock_get_all, mock_headwind
	):
		"""Existing doc with differing field -> frappe.db.set_value called with changed fields only"""
		api_item = {"name": "doc1", "field1": "new_value", "field2": "same"}
		existing_doc = frappe._dict({"name": "doc1", "field1": "old_value", "field2": "same"})
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = [existing_doc]

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1", "field2"])

		mock_set_value.assert_called_once_with("TestDoc", "doc1", {"field1": "new_value"})
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.set_value")
	@patch("frappe.db.commit")
	def test_existing_record_no_changes_skips_set_value(
		self, mock_commit, mock_set_value, mock_get_all, mock_headwind
	):
		"""Existing doc with all fields matching -> frappe.db.set_value NOT called"""
		api_item = {"name": "doc1", "field1": "value1", "field2": "value2"}
		existing_doc = frappe._dict({"name": "doc1", "field1": "value1", "field2": "value2"})
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = [existing_doc]

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1", "field2"])

		mock_set_value.assert_not_called()
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.set_value")
	@patch("frappe.db.commit")
	def test_stringified_comparison_int_vs_string_equal(
		self, mock_commit, mock_set_value, mock_get_all, mock_headwind
	):
		"""API int 5 vs doc string '5' -> stringified comparison -> equal -> no update"""
		api_item = {"name": "doc1", "count": 5}
		existing_doc = frappe._dict({"name": "doc1", "count": "5"})
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = [existing_doc]

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["count"])

		mock_set_value.assert_not_called()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.set_value")
	@patch("frappe.db.commit")
	def test_field_map_renames_api_field_to_frappe_field(
		self, mock_commit, mock_set_value, mock_get_all, mock_headwind
	):
		"""field_map={'api_name': 'frappe_name'} -> api_name read from doc as frappe_name, updated_fields keyed by frappe_name"""
		api_item = {"name": "doc1", "api_name": "new_value"}
		existing_doc = frappe._dict({"name": "doc1", "frappe_name": "old_value"})
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = [existing_doc]

		result = self.sync_doctype_from_api(
			"TestDoc", "headwind", "/endpoint", "name", ["api_name"], field_map={"api_name": "frappe_name"}
		)

		mock_set_value.assert_called_once_with("TestDoc", "doc1", {"frappe_name": "new_value"})
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.set_value")
	@patch("frappe.db.commit")
	def test_field_not_in_field_map_used_as_is(
		self, mock_commit, mock_set_value, mock_get_all, mock_headwind
	):
		"""api_field not in field_map -> used as-is for both doc read and updated_fields key"""
		api_item = {"name": "doc1", "field1": "new_value", "field2": "new_value2"}
		existing_doc = frappe._dict({"name": "doc1", "field1": "old_value", "field2": "old_value2"})
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = [existing_doc]

		result = self.sync_doctype_from_api(
			"TestDoc",
			"headwind",
			"/endpoint",
			"name",
			["field1", "field2"],
			field_map={"field1": "mapped_field1"},
		)

		mock_set_value.assert_called_once_with(
			"TestDoc", "doc1", {"mapped_field1": "new_value", "field2": "new_value2"}
		)
		self.assertEqual(result, "Sync complete")

	# ===== new record path (insert) =====

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.get_doc")
	@patch("frappe.db.commit")
	def test_new_record_creates_doc_with_key_field_and_api_fields(
		self, mock_commit, mock_get_doc, mock_get_all, mock_headwind
	):
		"""New item (no existing doc) -> frappe.get_doc called with doctype, name (key_field), and api_fields"""
		api_item = {"name": "doc1", "field1": "value1", "field2": "value2"}
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = []
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1", "field2"])

		mock_get_doc.assert_called_once_with(
			{"doctype": "TestDoc", "name": "doc1", "field1": "value1", "field2": "value2"}
		)
		mock_doc.insert.assert_called_once_with(ignore_permissions=True)
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.get_doc")
	@patch("frappe.db.commit")
	def test_new_record_with_field_map_renames_fields(
		self, mock_commit, mock_get_doc, mock_get_all, mock_headwind
	):
		"""New item with field_map -> frappe.get_doc called with mapped field names"""
		api_item = {"name": "doc1", "api_name": "value1"}
		mock_headwind.return_value = {"data": [api_item]}
		mock_get_all.return_value = []
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		result = self.sync_doctype_from_api(
			"TestDoc", "headwind", "/endpoint", "name", ["api_name"], field_map={"api_name": "frappe_name"}
		)

		mock_get_doc.assert_called_once_with({"doctype": "TestDoc", "name": "doc1", "frappe_name": "value1"})
		mock_doc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.get_doc")
	@patch("frappe.db.commit")
	def test_multiple_new_items_creates_each_separately(
		self, mock_commit, mock_get_doc, mock_get_all, mock_headwind
	):
		"""Multiple new items -> frappe.get_doc/.insert() called once per item"""
		api_items = [{"name": "doc1", "field1": "value1"}, {"name": "doc2", "field1": "value2"}]
		mock_headwind.return_value = {"data": api_items}
		mock_get_all.return_value = []
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1"])

		self.assertEqual(mock_get_doc.call_count, 2)
		self.assertEqual(mock_doc.insert.call_count, 2)
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")

	# ===== commit and error handling =====

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.db.commit")
	@patch("frappe.get_doc")
	@patch("frappe.db.set_value")
	@patch("frappe.get_all")
	def test_mixed_updates_and_inserts_commits_once(
		self, mock_get_all, mock_set_value, mock_get_doc, mock_commit, mock_headwind
	):
		"""Mix of updates and inserts -> frappe.db.commit() called exactly once at end"""
		api_items = [{"name": "doc1", "field1": "new_value"}, {"name": "doc2", "field1": "value2"}]
		existing_doc = frappe._dict({"name": "doc1", "field1": "old_value"})
		mock_headwind.return_value = {"data": api_items}
		mock_get_all.side_effect = [[existing_doc], []]
		mock_doc = MagicMock()
		mock_get_doc.return_value = mock_doc

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1"])

		mock_set_value.assert_called_once()
		mock_get_doc.assert_called_once()
		mock_doc.insert.assert_called_once()
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.commit")
	@patch("frappe.log_error")
	def test_exception_during_sync_caught_and_logged(
		self, mock_log_error, mock_commit, mock_get_all, mock_headwind
	):
		"""Exception during loop -> caught, frappe.log_error called with traceback and doctype name, returns 'Sync complete'"""
		mock_headwind.return_value = {"data": [{"name": "doc1", "field1": "value1"}]}
		mock_get_all.side_effect = RuntimeError("API error")

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1"])

		mock_log_error.assert_called_once()
		call_args = mock_log_error.call_args
		self.assertIn("TestDoc", call_args[0][1])
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.commit")
	def test_empty_items_list_commits_and_returns_complete(self, mock_commit, mock_get_all, mock_headwind):
		"""Empty items list -> loop never executes, frappe.db.commit() still called, returns 'Sync complete'"""
		mock_headwind.return_value = {"data": []}
		mock_get_all.return_value = []

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1"])

		mock_get_all.assert_not_called()
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")

	@patch("ivm.integrations.headwind.headwind_api_request")
	@patch("frappe.get_all")
	@patch("frappe.db.commit")
	def test_missing_data_key_defaults_to_empty_list(self, mock_commit, mock_get_all, mock_headwind):
		"""API response missing 'data' key -> defaults to empty list, no exception"""
		mock_headwind.return_value = {}
		mock_get_all.return_value = []

		result = self.sync_doctype_from_api("TestDoc", "headwind", "/endpoint", "name", ["field1"])

		mock_get_all.assert_not_called()
		mock_commit.assert_called_once()
		self.assertEqual(result, "Sync complete")
