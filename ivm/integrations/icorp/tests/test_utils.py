"""Tests for ivm.integrations.icorp.utils"""

import unittest

import frappe

from ivm.integrations.icorp.utils import (
	api_data_to_frappe_dict,
	convert_fields_to_bool,
	dict_keys_to_camel_case,
	dict_keys_to_snake_case,
	to_camel_case,
)


class TestToCamelCase(unittest.TestCase):
	"""to_camel_case function"""

	def test_converts_snake_case_to_camel_case(self):
		"""snake_case_field -> snakeCaseField"""
		self.assertEqual(to_camel_case("snake_case_field"), "snakeCaseField")

	def test_leaves_already_camel_case_unchanged(self):
		"""already -> already"""
		self.assertEqual(to_camel_case("already"), "already")

	def test_handles_empty_string(self):
		"""empty string -> empty string"""
		self.assertEqual(to_camel_case(""), "")

	def test_single_underscore(self):
		"""a_b -> aB"""
		self.assertEqual(to_camel_case("a_b"), "aB")

	def test_multiple_underscores(self):
		"""a_b_c_d -> aBCD"""
		self.assertEqual(to_camel_case("a_b_c_d"), "aBCD")


class TestDictKeysToCamelCase(unittest.TestCase):
	"""dict_keys_to_camel_case function"""

	def test_converts_top_level_keys(self):
		"""{"snake_key": 1} -> {"snakeKey": 1}"""
		result = dict_keys_to_camel_case({"snake_key": 1})
		self.assertEqual(result, {"snakeKey": 1})

	def test_multiple_keys(self):
		"""Multiple snake_case keys converted"""
		result = dict_keys_to_camel_case({"first_name": "John", "last_name": "Doe"})
		self.assertEqual(result, {"firstName": "John", "lastName": "Doe"})

	def test_preserves_values(self):
		"""Values unchanged, only keys converted"""
		result = dict_keys_to_camel_case({"snake_key": {"nested": "value"}})
		self.assertEqual(result, {"snakeKey": {"nested": "value"}})

	def test_empty_dict(self):
		"""Empty dict returns empty dict"""
		self.assertEqual(dict_keys_to_camel_case({}), {})


class TestDictKeysToSnakeCase(unittest.TestCase):
	"""dict_keys_to_snake_case function"""

	def test_converts_camel_case_to_snake_case(self):
		"""{"camelCase": 1} -> {"camel_case": 1}"""
		result = dict_keys_to_snake_case({"camelCase": 1})
		self.assertEqual(result, {"camel_case": 1})

	def test_nested_dicts(self):
		"""Recursively converts nested dict keys"""
		input_data = {"outerKey": {"innerKey": "value"}}
		expected = {"outer_key": {"inner_key": "value"}}
		result = dict_keys_to_snake_case(input_data)
		self.assertEqual(result, expected)

	def test_list_of_dicts(self):
		"""Converts keys in dicts within lists"""
		input_data = [{"camelCase": 1}, {"anotherKey": 2}]
		expected = [{"camel_case": 1}, {"another_key": 2}]
		result = dict_keys_to_snake_case(input_data)
		self.assertEqual(result, expected)

	def test_mixed_nesting(self):
		"""Handles deeply nested mixed structures"""
		input_data = {
			"topLevel": [
				{"nestedKey": "value"},
				{"anotherNested": {"deepKey": "deep_value"}},
			]
		}
		expected = {
			"top_level": [
				{"nested_key": "value"},
				{"another_nested": {"deep_key": "deep_value"}},
			]
		}
		result = dict_keys_to_snake_case(input_data)
		self.assertEqual(result, expected)

	def test_non_dict_non_list_passthrough(self):
		"""Scalar values pass through unchanged"""
		self.assertEqual(dict_keys_to_snake_case("string"), "string")
		self.assertEqual(dict_keys_to_snake_case(42), 42)
		self.assertEqual(dict_keys_to_snake_case(None), None)

	def test_empty_dict(self):
		"""Empty dict returns empty dict"""
		self.assertEqual(dict_keys_to_snake_case({}), {})

	def test_empty_list(self):
		"""Empty list returns empty list"""
		self.assertEqual(dict_keys_to_snake_case([]), [])


class TestApiDataToFrappeDict(unittest.TestCase):
	"""api_data_to_frappe_dict function"""

	def test_converts_list_of_dicts_to_frappe_dicts(self):
		"""List of dicts -> list of frappe._dict with .name set"""
		data = [{"id": 1, "name_field": "Alice"}, {"id": 2, "name_field": "Bob"}]
		result = api_data_to_frappe_dict(data, "id")
		self.assertEqual(len(result), 2)
		self.assertIsInstance(result[0], frappe._dict)
		self.assertEqual(result[0].name, "1")
		self.assertEqual(result[1].name, "2")

	def test_sets_name_from_key_field(self):
		"""name attribute set from key_field value"""
		data = [{"user_id": 123, "username": "john"}]
		result = api_data_to_frappe_dict(data, "user_id")
		self.assertEqual(result[0].name, "123")

	def test_preserves_all_fields(self):
		"""All original fields preserved in frappe._dict"""
		data = [{"id": 1, "field_a": "value_a", "field_b": "value_b"}]
		result = api_data_to_frappe_dict(data, "id")
		self.assertEqual(result[0].field_a, "value_a")
		self.assertEqual(result[0].field_b, "value_b")

	def test_handles_empty_list(self):
		"""Empty list returns empty list"""
		result = api_data_to_frappe_dict([], "id")
		self.assertEqual(result, [])

	def test_handles_none_data(self):
		"""None data treated as empty list"""
		result = api_data_to_frappe_dict(None, "id")
		self.assertEqual(result, [])

	def test_converts_key_field_value_to_string(self):
		"""Key field value converted to string for .name"""
		data = [{"id": 999, "label": "test"}]
		result = api_data_to_frappe_dict(data, "id")
		self.assertEqual(result[0].name, "999")
		self.assertIsInstance(result[0].name, str)


class TestConvertFieldsToBool(unittest.TestCase):
	"""convert_fields_to_bool function"""

	def test_converts_string_true_values(self):
		"""String 'true' -> True"""
		data = {"active": "true"}
		result = convert_fields_to_bool(data, ["active"])
		self.assertIs(result["active"], True)

	def test_converts_string_1_to_true(self):
		"""String '1' -> True"""
		data = {"enabled": "1"}
		result = convert_fields_to_bool(data, ["enabled"])
		self.assertIs(result["enabled"], True)

	def test_converts_string_yes_to_true(self):
		"""String 'yes' -> True"""
		data = {"confirmed": "yes"}
		result = convert_fields_to_bool(data, ["confirmed"])
		self.assertIs(result["confirmed"], True)

	def test_converts_string_false_to_false(self):
		"""String 'false' -> False"""
		data = {"active": "false"}
		result = convert_fields_to_bool(data, ["active"])
		self.assertIs(result["active"], False)

	def test_converts_integer_0_to_false(self):
		"""Integer 0 -> False"""
		data = {"count": 0}
		result = convert_fields_to_bool(data, ["count"])
		self.assertIs(result["count"], False)

	def test_converts_integer_1_to_true(self):
		"""Integer 1 -> True"""
		data = {"count": 1}
		result = convert_fields_to_bool(data, ["count"])
		self.assertIs(result["count"], True)

	def test_converts_multiple_fields(self):
		"""Multiple fields converted in one call"""
		data = {"active": "true", "enabled": "false", "count": 1}
		result = convert_fields_to_bool(data, ["active", "enabled", "count"])
		self.assertIs(result["active"], True)
		self.assertIs(result["enabled"], False)
		self.assertIs(result["count"], True)

	def test_case_insensitive_string_matching(self):
		"""String matching is case-insensitive"""
		data = {"field1": "TRUE", "field2": "False", "field3": "YES"}
		result = convert_fields_to_bool(data, ["field1", "field2", "field3"])
		self.assertIs(result["field1"], True)
		self.assertIs(result["field2"], False)
		self.assertIs(result["field3"], True)

	def test_modifies_dict_in_place(self):
		"""Function modifies dict in place and returns it"""
		data = {"active": "true"}
		result = convert_fields_to_bool(data, ["active"])
		self.assertIs(result, data)

	def test_missing_fields_converted_to_false(self):
		"""Missing fields in field_names list are converted to False"""
		data = {"active": "true"}
		result = convert_fields_to_bool(data, ["active", "missing_field"])
		self.assertIs(result["active"], True)
		self.assertIs(result["missing_field"], False)

	def test_non_string_non_zero_values_are_truthy(self):
		"""Non-string, non-zero values coerced to bool"""
		data = {"field1": 5, "field2": [], "field3": [1, 2]}
		result = convert_fields_to_bool(data, ["field1", "field2", "field3"])
		self.assertIs(result["field1"], True)
		self.assertIs(result["field2"], False)
		self.assertIs(result["field3"], True)
