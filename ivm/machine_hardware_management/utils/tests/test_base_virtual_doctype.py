from datetime import UTC, datetime
from typing import ClassVar
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.machine_hardware_management.utils.base_virtual_doctype import BaseVirtualDoctype

patch("frappe.db.estimate_count", return_value=0).start()


class _TestVirtualDoc(BaseVirtualDoctype):
	API_TYPE = "icorp"
	endpoint = "/api/test"
	FIELD_MAP: ClassVar[dict] = {"name": "id", "title": "title_field", "status": "status_field"}
	SORT_FIELD_MAP: ClassVar[dict] = {"title": "title_field"}
	BOOL_FIELDS: ClassVar[list] = ["is_active"]


class _TestVirtualDocHeadwind(BaseVirtualDoctype):
	API_TYPE = "headwind"
	endpoint = "/api/headwind/test"
	FIELD_MAP: ClassVar[dict] = {"name": "id", "title": "title_field"}
	BOOL_FIELDS: ClassVar[list] = []


class TestBaseVirtualDoctypeGetList(FrappeTestCase):
	def test_get_list_normal_response(self):
		api_response = {
			"data": [
				{"id": "1", "title_field": "Item 1", "status_field": "active"},
				{"id": "2", "title_field": "Item 2", "status_field": "inactive"},
			]
		}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
				return_value={},
			):
				mock_cache = MagicMock()
				mock_cache.get_value.return_value = None
				with patch(
					"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe.cache",
					return_value=mock_cache,
				):
					mock_get.return_value = api_response
					result = _TestVirtualDoc.get_list({"page_length": 20, "start": 0})
					self.assertEqual(len(result), 2)
					self.assertEqual(result[0].name, "1")
					self.assertEqual(result[0].id, "1")
					self.assertEqual(result[0].title_field, "Item 1")
					self.assertEqual(result[1].name, "2")

	def test_get_list_empty_response(self):
		api_response = {"data": []}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
				return_value={},
			):
				mock_cache = MagicMock()
				mock_cache.get_value.return_value = None
				with patch(
					"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe.cache",
					return_value=mock_cache,
				):
					mock_get.return_value = api_response
					result = _TestVirtualDoc.get_list({"page_length": 20, "start": 0})
					self.assertEqual(result, [])

	def test_get_list_cache_hit(self):
		api_response = {"data": [{"id": "1", "title_field": "Item 1"}]}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			mock_cache = MagicMock()
			cached_result = [{"id": "1", "title_field": "Item 1", "name": "1"}]
			mock_cache.get_value.side_effect = [None, cached_result]
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe.cache",
				return_value=mock_cache,
			):
				mock_get.return_value = api_response
				args = {"page_length": 20, "start": 0}
				result1 = _TestVirtualDoc.get_list(args)
				result2 = _TestVirtualDoc.get_list(args)
				self.assertEqual(mock_get.call_count, 1)
				self.assertEqual(result1, result2)

	def test_get_list_pagination_math(self):
		api_response = {"data": []}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			mock_cache = MagicMock()
			mock_cache.get_value.return_value = None
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe.cache",
				return_value=mock_cache,
			):
				mock_get.return_value = api_response
				_TestVirtualDoc.get_list({"page_length": 10, "start": 20})
				call_args = mock_get.call_args[0][0]
				self.assertIn("page=3", call_args)
				self.assertIn("pageSize=10", call_args)


class TestBaseVirtualDoctypeBuildListApiParams(FrappeTestCase):
	def test_build_list_api_params_icorp_sort(self):
		with patch(
			"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
			return_value={},
		):
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_sort_to_dict"
			) as mock_sort:
				mock_sort.return_value = {"sortField": "title_field", "sortOrder": "asc"}
				params = _TestVirtualDoc.build_list_api_params(
					{"page_length": 20, "start": 0, "order_by": "title asc"}
				)
				self.assertIn("sort[0].parameterName", params)
				self.assertEqual(params["sort[0].parameterName"], "title_field")
				self.assertEqual(params["sort[0].sortOrder"], "asc")
				self.assertNotIn("sortField", params)

	def test_build_list_api_params_headwind_page_rename(self):
		with patch(
			"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
			return_value={},
		):
			params = _TestVirtualDocHeadwind.build_list_api_params({"page_length": 20, "start": 0})
			self.assertIn("pageNum", params)
			self.assertNotIn("page", params)
			self.assertEqual(params["pageNum"], 1)

	def test_build_list_api_params_unknown_api_type_raises(self):
		class _BadVirtualDoc(BaseVirtualDoctype):
			API_TYPE = "unknown"
			endpoint = "/api/bad"

		with patch(
			"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
			return_value={},
		):
			with self.assertRaises(ValueError) as ctx:
				_BadVirtualDoc.build_list_api_params({"page_length": 20, "start": 0})
			self.assertIn("Unknown API_TYPE", str(ctx.exception))

	def test_build_list_api_params_sanitize_order_by_sql_expressions(self):
		with patch(
			"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
			return_value={},
		):
			params_ifnull = _TestVirtualDoc.build_list_api_params(
				{"page_length": 20, "start": 0, "order_by": "ifnull(title, 'default') asc"}
			)
			self.assertNotIn("sortField", params_ifnull)
			params_coalesce = _TestVirtualDoc.build_list_api_params(
				{"page_length": 20, "start": 0, "order_by": "coalesce(title, status) asc"}
			)
			self.assertNotIn("sortField", params_coalesce)
			params_parens = _TestVirtualDoc.build_list_api_params(
				{"page_length": 20, "start": 0, "order_by": "(title) asc"}
			)
			self.assertNotIn("sortField", params_parens)


class TestBaseVirtualDoctypeLoadFromDb(FrappeTestCase):
	def test_load_from_db_normal(self):
		api_response = {"data": {"id": "123", "title_field": "Test Item"}}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.ensure_meta_is_ready"):
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get"
			) as mock_get:
				with patch(
					"ivm.machine_hardware_management.utils.base_virtual_doctype.set_attrs_from_dict"
				) as mock_set:
					doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
					doc.name = "123"
					doc.doctype = "_TestVirtualDoc"
					mock_get.return_value = api_response
					doc.load_from_db()
					mock_get.assert_called_once()
					mock_set.assert_called_once()

	def test_load_from_db_new_doc_skips_api(self):
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
			doc.name = "new-123"
			doc.doctype = "_TestVirtualDoc"
			doc.load_from_db()
			mock_get.assert_not_called()

	def test_load_from_db_api_exception_reraises(self):
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.ensure_meta_is_ready"):
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get"
			) as mock_get:
				doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
				doc.name = "123"
				doc.doctype = "_TestVirtualDoc"
				mock_get.side_effect = Exception("API error")
				with self.assertRaises(Exception):
					doc.load_from_db()


class TestBaseVirtualDoctypeDbInsert(FrappeTestCase):
	def test_db_insert_normal(self):
		doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
		doc.doctype = "_TestVirtualDoc"
		doc.title = "New Item"
		doc.is_active = True
		api_response = {"data": {"id": "999", "title_field": "New Item"}}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_post") as mock_post:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.convert_fields_to_bool"
			) as mock_bool:
				with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.set_attrs_from_dict"):
					with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.clear_cache"):
						with patch.object(doc, "get_valid_dict", return_value={"title": "New Item"}):
							mock_post.return_value = api_response
							mock_bool.return_value = {"title": "New Item", "is_active": True}
							doc.db_insert()
							self.assertEqual(doc.name, "999")
							mock_post.assert_called_once()

	def test_db_insert_api_exception_reraises(self):
		doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
		doc.doctype = "_TestVirtualDoc"
		doc.title = "New Item"
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_post") as mock_post:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.convert_fields_to_bool"
			) as mock_bool:
				with patch.object(doc, "get_valid_dict", return_value={"title": "New Item"}):
					mock_post.side_effect = Exception("API error")
					mock_bool.return_value = {"title": "New Item"}
					with self.assertRaises(Exception):
						doc.db_insert()


class TestBaseVirtualDoctypeDbUpdate(FrappeTestCase):
	def test_db_update_normal(self):
		doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
		doc.doctype = "_TestVirtualDoc"
		doc.name = "123"
		doc.title = "Updated Item"
		api_response = {"data": {"id": "123", "title_field": "Updated Item"}}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_put") as mock_put:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.convert_fields_to_bool"
			) as mock_bool:
				with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.set_attrs_from_dict"):
					with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.clear_cache"):
						with patch.object(doc, "get_valid_dict", return_value={"title": "Updated Item"}):
							mock_put.return_value = api_response
							mock_bool.return_value = {"title": "Updated Item"}
							doc.db_update()
							mock_put.assert_called_once()

	def test_db_update_api_exception_reraises(self):
		doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
		doc.doctype = "_TestVirtualDoc"
		doc.name = "123"
		doc.title = "Updated Item"
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_put") as mock_put:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.convert_fields_to_bool"
			) as mock_bool:
				with patch.object(doc, "get_valid_dict", return_value={"title": "Updated Item"}):
					mock_put.side_effect = Exception("API error")
					mock_bool.return_value = {"title": "Updated Item"}
					with self.assertRaises(Exception):
						doc.db_update()


class TestBaseVirtualDoctypeDelete(FrappeTestCase):
	def test_delete_icorp_success(self):
		doc = _TestVirtualDoc.__new__(_TestVirtualDoc)
		doc.doctype = "_TestVirtualDoc"
		doc.name = "123"
		api_response = {"data": {}}
		with patch(
			"ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_delete"
		) as mock_delete:
			with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.clear_cache"):
				mock_delete.return_value = api_response
				doc.delete()
				mock_delete.assert_called_once()

	def test_delete_headwind_not_implemented(self):
		doc = _TestVirtualDocHeadwind.__new__(_TestVirtualDocHeadwind)
		doc.doctype = "_TestVirtualDocHeadwind"
		doc.name = "123"
		with self.assertRaises(NotImplementedError):
			doc.delete()


class TestBaseVirtualDoctypeGetCount(FrappeTestCase):
	def test_get_count_normal_response(self):
		api_response = {"pagination": {"total_records": 42}}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
				return_value={},
			):
				mock_cache = MagicMock()
				mock_cache.get_value.return_value = None
				with patch(
					"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe.cache",
					return_value=mock_cache,
				):
					mock_get.return_value = api_response
					count = _TestVirtualDoc.get_count({"page_length": 20, "start": 0})
					self.assertEqual(count, 42)

	def test_get_count_cache_hit(self):
		api_response = {"pagination": {"total_records": 42}}
		with patch("ivm.machine_hardware_management.utils.base_virtual_doctype.icorp_api_get") as mock_get:
			with patch(
				"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe_filters_to_dict",
				return_value={},
			):
				mock_cache = MagicMock()
				mock_cache.get_value.side_effect = [None, 42]
				with patch(
					"ivm.machine_hardware_management.utils.base_virtual_doctype.frappe.cache",
					return_value=mock_cache,
				):
					mock_get.return_value = api_response
					args = {"page_length": 20, "start": 0}
					count1 = _TestVirtualDoc.get_count(args)
					count2 = _TestVirtualDoc.get_count(args)
					self.assertEqual(mock_get.call_count, 1)
					self.assertEqual(count1, count2)
