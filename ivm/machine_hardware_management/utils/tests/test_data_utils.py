import types
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.machine_hardware_management.utils.data_utils import (
	_parse_order_by,
	build_sort_params,
	ensure_meta_is_ready,
	normalize_child_table_field,
	set_attrs_from_dict,
	to_iso8601,
)


class TestParseOrderBy(FrappeTestCase):
	def test_none_input_returns_none_tuple(self):
		field, direction = _parse_order_by(None)
		self.assertIsNone(field)
		self.assertIsNone(direction)

	def test_empty_string_returns_none_tuple(self):
		field, direction = _parse_order_by("")
		self.assertIsNone(field)
		self.assertIsNone(direction)

	def test_whitespace_only_returns_none_tuple(self):
		field, direction = _parse_order_by("   ")
		self.assertIsNone(field)
		self.assertIsNone(direction)

	def test_simple_fieldname_defaults_to_asc(self):
		field, direction = _parse_order_by("fieldname")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "ASC")

	def test_fieldname_with_desc_direction(self):
		field, direction = _parse_order_by("fieldname desc")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "DESC")

	def test_fieldname_with_asc_direction(self):
		field, direction = _parse_order_by("fieldname asc")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "ASC")

	def test_uppercase_direction_case_insensitive(self):
		field, direction = _parse_order_by("fieldname DESC")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "DESC")

	def test_uppercase_asc_case_insensitive(self):
		field, direction = _parse_order_by("fieldname ASC")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "ASC")

	def test_mixed_case_direction(self):
		field, direction = _parse_order_by("fieldname DeSc")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "DESC")

	def test_table_prefixed_fieldname(self):
		field, direction = _parse_order_by("tabMachine.fieldname desc")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "DESC")

	def test_backtick_quoted_table_and_field(self):
		field, direction = _parse_order_by("`tabMachine`.`fieldname` desc")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "DESC")

	def test_backtick_quoted_field_only(self):
		field, direction = _parse_order_by("`fieldname`")
		self.assertEqual(field, "fieldname")
		self.assertEqual(direction, "ASC")

	def test_multiple_comma_separated_clauses_uses_first(self):
		field, direction = _parse_order_by("field1 desc, field2 asc")
		self.assertEqual(field, "field1")
		self.assertEqual(direction, "DESC")

	def test_url_encoded_space_via_plus(self):
		field, direction = _parse_order_by("field+desc")
		self.assertEqual(field, "field")
		self.assertEqual(direction, "DESC")

	def test_url_encoded_space_via_percent(self):
		field, direction = _parse_order_by("field%20desc")
		self.assertEqual(field, "field")
		self.assertEqual(direction, "DESC")

	def test_garbage_unparseable_input(self):
		# Regex [^.\s]+ matches any non-dot, non-whitespace chars, so !@#$%^&*() is valid field name
		field, direction = _parse_order_by("!@#$%^&*()")
		self.assertEqual(field, "!@#$%^&*()")
		self.assertEqual(direction, "ASC")

	def test_garbage_with_invalid_direction(self):
		field, direction = _parse_order_by("fieldname invalid_dir")
		self.assertIsNone(field)
		self.assertIsNone(direction)


class TestBuildSortParams(FrappeTestCase):
	def test_order_by_resolves_to_none_returns_empty_list(self):
		result = build_sort_params(None, {})
		self.assertEqual(result, [])

	def test_order_by_empty_string_returns_empty_list(self):
		result = build_sort_params("", {})
		self.assertEqual(result, [])

	def test_field_in_sort_field_map_uses_mapped_value(self):
		sort_field_map = {"fieldname": "mappedFieldName"}
		result = build_sort_params("fieldname asc", sort_field_map)
		self.assertEqual(result[0], ("sort[0].parameterName", "mappedFieldName"))
		self.assertEqual(result[1], ("sort[0].sortOrder", "ASC"))

	def test_field_not_in_map_falls_back_to_camel_case(self):
		with patch("ivm.machine_hardware_management.utils.data_utils.to_camel_case") as mock_camel:
			mock_camel.return_value = "fieldNameCamelCase"
			result = build_sort_params("field_name asc", {})
			self.assertEqual(result[0], ("sort[0].parameterName", "fieldNameCamelCase"))
			mock_camel.assert_called_once_with("field_name")

	def test_creation_field_always_maps_to_created_date(self):
		result = build_sort_params("creation asc", {})
		self.assertEqual(result[0], ("sort[0].parameterName", "createdDate"))

	def test_creation_field_with_explicit_map_still_uses_hardcoded_alias(self):
		sort_field_map = {"creation": "customCreationField"}
		result = build_sort_params("creation asc", sort_field_map)
		self.assertEqual(result[0], ("sort[0].parameterName", "createdDate"))

	def test_add_tie_breaker_false_returns_only_sort_0(self):
		result = build_sort_params("fieldname asc", {}, add_tie_breaker=False)
		self.assertEqual(len(result), 2)
		self.assertEqual(result[0][0], "sort[0].parameterName")
		self.assertEqual(result[1][0], "sort[0].sortOrder")

	def test_add_tie_breaker_true_includes_sort_1(self):
		result = build_sort_params("fieldname asc", {}, add_tie_breaker=True)
		self.assertEqual(len(result), 4)
		self.assertEqual(result[2][0], "sort[1].parameterName")
		self.assertEqual(result[3][0], "sort[1].sortOrder")

	def test_tie_breaker_with_name_in_map(self):
		sort_field_map = {"name": "customNameField"}
		result = build_sort_params("fieldname asc", sort_field_map, add_tie_breaker=True)
		self.assertEqual(result[2], ("sort[1].parameterName", "customNameField"))
		self.assertEqual(result[3], ("sort[1].sortOrder", "ASC"))

	def test_tie_breaker_with_id_in_map_when_name_absent(self):
		sort_field_map = {"id": "customIdField"}
		result = build_sort_params("fieldname asc", sort_field_map, add_tie_breaker=True)
		self.assertEqual(result[2], ("sort[1].parameterName", "customIdField"))

	def test_tie_breaker_fallback_to_literal_id_when_no_name_or_id(self):
		result = build_sort_params("fieldname asc", {}, add_tie_breaker=True)
		self.assertEqual(result[2], ("sort[1].parameterName", "Id"))
		self.assertEqual(result[3], ("sort[1].sortOrder", "ASC"))

	def test_tie_breaker_prefers_name_over_id(self):
		sort_field_map = {"name": "nameField", "id": "idField"}
		result = build_sort_params("fieldname asc", sort_field_map, add_tie_breaker=True)
		self.assertEqual(result[2], ("sort[1].parameterName", "nameField"))

	def test_returned_list_is_list_of_tuples(self):
		result = build_sort_params("fieldname asc", {})
		self.assertIsInstance(result, list)
		for item in result:
			self.assertIsInstance(item, tuple)
			self.assertEqual(len(item), 2)


class TestSetAttrsFromDict(FrappeTestCase):
	def setUp(self):
		self.mock_obj = types.SimpleNamespace(doctype="Machine")
		self.mock_obj.set = MagicMock()

	def test_empty_data_dict_no_attributes_set(self):
		set_attrs_from_dict(self.mock_obj, {})
		self.mock_obj.set.assert_not_called()

	def test_none_data_no_attributes_set(self):
		set_attrs_from_dict(self.mock_obj, None)
		self.mock_obj.set.assert_not_called()

	def test_key_name_remapped_to_doctype_name(self):
		set_attrs_from_dict(self.mock_obj, {"name": "test_name"})
		self.assertEqual(self.mock_obj.machine_name, "test_name")

	def test_doctype_name_lowercased(self):
		self.mock_obj.doctype = "MyMachine"
		set_attrs_from_dict(self.mock_obj, {"name": "test_name"})
		self.assertEqual(self.mock_obj.mymachine_name, "test_name")

	def test_key_in_child_table_map_calls_set(self):
		child_table_map = {"items": "item_field"}
		data = {"items": [{"item_field": "item1"}, {"item_field": "item2"}]}
		set_attrs_from_dict(self.mock_obj, data, child_table_map)
		self.mock_obj.set.assert_called_once()
		call_args = self.mock_obj.set.call_args
		self.assertEqual(call_args[0][0], "items")
		rows = call_args[0][1]
		self.assertEqual(len(rows), 2)
		self.assertIsInstance(rows[0], frappe._dict)

	def test_id_suffixed_key_with_none_coerced_to_empty_string(self):
		# Note: endswith("id") is case-sensitive, so "machineId" does NOT match (ends with "Id")
		# Only lowercase "id" suffix triggers coercion
		set_attrs_from_dict(self.mock_obj, {"machineid": None})
		self.assertEqual(self.mock_obj.machineid, "")

	def test_id_suffixed_key_with_number_coerced_to_string(self):
		# endswith("id") is case-sensitive, so use lowercase suffix
		set_attrs_from_dict(self.mock_obj, {"machineid": 123})
		self.assertEqual(self.mock_obj.machineid, "123")

	def test_id_suffixed_key_with_list_not_stringified(self):
		set_attrs_from_dict(self.mock_obj, {"machineId": [1, 2, 3]})
		self.assertEqual(self.mock_obj.machineId, [1, 2, 3])

	def test_id_suffixed_key_with_dict_not_stringified(self):
		set_attrs_from_dict(self.mock_obj, {"machineId": {"key": "value"}})
		self.assertEqual(self.mock_obj.machineId, {"key": "value"})

	def test_capital_id_suffix_not_coerced(self):
		# "machineId" ends with "Id" (capital), not "id", so coercion does NOT apply
		set_attrs_from_dict(self.mock_obj, {"machineId": 123})
		self.assertEqual(self.mock_obj.machineId, 123)

	def test_string_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": "string_value"})
		self.assertEqual(self.mock_obj.fieldname, "string_value")

	def test_int_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": 42})
		self.assertEqual(self.mock_obj.fieldname, 42)

	def test_float_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": 3.14})
		self.assertEqual(self.mock_obj.fieldname, 3.14)

	def test_bool_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": True})
		self.assertEqual(self.mock_obj.fieldname, True)

	def test_none_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": None})
		self.assertIsNone(self.mock_obj.fieldname)

	def test_list_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": [1, 2, 3]})
		self.assertEqual(self.mock_obj.fieldname, [1, 2, 3])

	def test_dict_value_passed_through_unchanged(self):
		set_attrs_from_dict(self.mock_obj, {"fieldname": {"key": "value"}})
		self.assertEqual(self.mock_obj.fieldname, {"key": "value"})

	def test_exotic_type_coerced_to_string(self):
		exotic_obj = datetime(2024, 1, 15, 10, 30, 0)
		set_attrs_from_dict(self.mock_obj, {"fieldname": exotic_obj})
		self.assertEqual(self.mock_obj.fieldname, str(exotic_obj))

	def test_multiple_keys_all_set(self):
		data = {"name": "test_name", "fieldname": "value", "machineid": 123}
		set_attrs_from_dict(self.mock_obj, data)
		self.assertEqual(self.mock_obj.machine_name, "test_name")
		self.assertEqual(self.mock_obj.fieldname, "value")
		self.assertEqual(self.mock_obj.machineid, "123")


class TestNormalizeChildTableField(FrappeTestCase):
	def test_empty_list_returns_empty_list(self):
		result = normalize_child_table_field([], "item_field")
		self.assertEqual(result, [])

	def test_none_returns_empty_list(self):
		result = normalize_child_table_field(None, "item_field")
		self.assertEqual(result, [])

	def test_list_of_dicts_extracts_child_field(self):
		value = [{"item_field": "item1"}, {"item_field": "item2"}]
		result = normalize_child_table_field(value, "item_field")
		self.assertEqual(len(result), 2)
		self.assertEqual(result[0]["item_field"], "item1")
		self.assertEqual(result[0]["idx"], 1)
		self.assertEqual(result[1]["item_field"], "item2")
		self.assertEqual(result[1]["idx"], 2)

	def test_list_of_dicts_missing_child_field_defaults_to_empty_string(self):
		value = [{"item_field": "item1"}, {"other_field": "value"}]
		result = normalize_child_table_field(value, "item_field")
		self.assertEqual(result[0]["item_field"], "item1")
		self.assertEqual(result[1]["item_field"], "")

	def test_list_of_scalars_stringified_with_idx(self):
		value = [1, 2, 3]
		result = normalize_child_table_field(value, "item_field")
		self.assertEqual(len(result), 3)
		self.assertEqual(result[0], {"item_field": "1", "idx": 1})
		self.assertEqual(result[1], {"item_field": "2", "idx": 2})
		self.assertEqual(result[2], {"item_field": "3", "idx": 3})

	def test_list_of_string_scalars(self):
		value = ["item1", "item2", "item3"]
		result = normalize_child_table_field(value, "item_field")
		self.assertEqual(len(result), 3)
		self.assertEqual(result[0], {"item_field": "item1", "idx": 1})
		self.assertEqual(result[2], {"item_field": "item3", "idx": 3})

	def test_single_scalar_string_value_behavior(self):
		# Test actual behavior: single string not in list gets iterated as characters
		value = "abc"
		result = normalize_child_table_field(value, "item_field")
		# String is iterable, so it becomes ["a", "b", "c"]
		self.assertEqual(len(result), 3)
		self.assertEqual(result[0]["item_field"], "a")
		self.assertEqual(result[1]["item_field"], "b")
		self.assertEqual(result[2]["item_field"], "c")

	def test_single_scalar_number_raises_type_error(self):
		# A bare int is truthy, so `value or []` keeps it as 42, then
		# `for x in 42` always raises -- ints are never iterable.
		with self.assertRaises(TypeError):
			normalize_child_table_field(42, "item_field")

	def test_idx_is_one_based(self):
		value = ["a", "b"]
		result = normalize_child_table_field(value, "item_field")
		self.assertEqual(result[0]["idx"], 1)
		self.assertEqual(result[1]["idx"], 2)


class TestToIso8601(FrappeTestCase):
	def test_datetime_format_with_space(self):
		result = to_iso8601("2024-01-15 10:30:00")
		self.assertEqual(result, "2024-01-15T10:30:00")

	def test_datetime_format_with_t(self):
		result = to_iso8601("2024-01-15T10:30:00")
		self.assertEqual(result, "2024-01-15T10:30:00")

	def test_unparseable_string_logs_error_twice_and_returns_original(self):
		with patch("ivm.machine_hardware_management.utils.data_utils.frappe.log_error") as mock_log:
			result = to_iso8601("garbage_date_string")
			self.assertEqual(result, "garbage_date_string")
			self.assertEqual(mock_log.call_count, 2)

	def test_unparseable_string_error_message_format(self):
		with patch("ivm.machine_hardware_management.utils.data_utils.frappe.log_error") as mock_log:
			to_iso8601("invalid")
			# Each call should have the error message and category
			for call_obj in mock_log.call_args_list:
				args = call_obj[0]
				self.assertIn("Failed to parse date string", args[0])
				self.assertEqual(args[1], "DateTimeHelper.to_iso8601 error")

	def test_none_input_behavior(self):
		# strptime raises TypeError on None, caught as Exception, logged, returns original None
		result = to_iso8601(None)
		self.assertIsNone(result)

	def test_iso8601_output_has_seconds_precision(self):
		result = to_iso8601("2024-01-15 10:30:45")
		self.assertIn("10:30:45", result)
		# Should not have microseconds
		self.assertNotIn(".", result)

	def test_various_valid_dates(self):
		test_cases = [
			("2024-12-31 23:59:59", "2024-12-31T23:59:59"),
			("2000-01-01T00:00:00", "2000-01-01T00:00:00"),
			("2024-06-15 14:22:33", "2024-06-15T14:22:33"),
		]
		for input_str, expected in test_cases:
			result = to_iso8601(input_str)
			self.assertEqual(result, expected)


class TestEnsureMetaIsReady(FrappeTestCase):
	def test_object_without_meta_calls_get_meta(self):
		mock_obj = types.SimpleNamespace(doctype="Machine")
		mock_meta = MagicMock()
		mock_meta.get_table_fields.return_value = []

		with patch("ivm.machine_hardware_management.utils.data_utils.frappe.get_meta") as mock_get_meta:
			mock_get_meta.return_value = mock_meta
			ensure_meta_is_ready(mock_obj)
			mock_get_meta.assert_called_once_with("Machine")
			self.assertEqual(mock_obj.meta, mock_meta)

	def test_object_with_existing_meta_does_not_call_get_meta(self):
		existing_meta = MagicMock()
		mock_obj = types.SimpleNamespace(doctype="Machine", meta=existing_meta)
		mock_obj._table_fieldnames = []

		with patch("ivm.machine_hardware_management.utils.data_utils.frappe.get_meta") as mock_get_meta:
			ensure_meta_is_ready(mock_obj)
			mock_get_meta.assert_not_called()
			self.assertEqual(mock_obj.meta, existing_meta)

	def test_object_with_falsy_meta_calls_get_meta(self):
		mock_obj = types.SimpleNamespace(doctype="Machine", meta=None)
		mock_meta = MagicMock()
		mock_meta.get_table_fields.return_value = []

		with patch("ivm.machine_hardware_management.utils.data_utils.frappe.get_meta") as mock_get_meta:
			mock_get_meta.return_value = mock_meta
			ensure_meta_is_ready(mock_obj)
			mock_get_meta.assert_called_once()

	def test_object_without_table_fieldnames_populates_from_meta(self):
		mock_field_1 = MagicMock(fieldname="field1")
		mock_field_2 = MagicMock(fieldname="field2")
		mock_meta = MagicMock()
		mock_meta.get_table_fields.return_value = [mock_field_1, mock_field_2]

		mock_obj = types.SimpleNamespace(doctype="Machine", meta=mock_meta)

		ensure_meta_is_ready(mock_obj)
		self.assertEqual(mock_obj._table_fieldnames, ["field1", "field2"])

	def test_object_with_existing_table_fieldnames_does_not_recompute(self):
		mock_meta = MagicMock()
		existing_fieldnames = ["existing1", "existing2"]
		mock_obj = types.SimpleNamespace(
			doctype="Machine", meta=mock_meta, _table_fieldnames=existing_fieldnames
		)

		ensure_meta_is_ready(mock_obj)
		mock_meta.get_table_fields.assert_not_called()
		self.assertEqual(mock_obj._table_fieldnames, existing_fieldnames)

	def test_full_flow_new_object(self):
		mock_field_1 = MagicMock(fieldname="items")
		mock_field_2 = MagicMock(fieldname="components")
		mock_meta = MagicMock()
		mock_meta.get_table_fields.return_value = [mock_field_1, mock_field_2]

		mock_obj = types.SimpleNamespace(doctype="Machine")

		with patch("ivm.machine_hardware_management.utils.data_utils.frappe.get_meta") as mock_get_meta:
			mock_get_meta.return_value = mock_meta
			ensure_meta_is_ready(mock_obj)
			self.assertEqual(mock_obj.meta, mock_meta)
			self.assertEqual(mock_obj._table_fieldnames, ["items", "components"])
