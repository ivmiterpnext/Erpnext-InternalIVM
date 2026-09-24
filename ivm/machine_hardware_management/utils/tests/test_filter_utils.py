import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from ivm.machine_hardware_management.utils.filter_utils import (
	DEFAULT_FIELD_MAP,
	_to_list,
	filters_to_query_params,
	frappe_filters_to_dict,
	frappe_sort_to_dict,
	replace_machine_id_with_name,
)


class TestToList(unittest.TestCase):
	def test_none_returns_empty_list(self):
		self.assertEqual(_to_list(None), [])

	def test_list_input_stringified(self):
		result = _to_list([1, 2, 3])
		self.assertEqual(result, ["1", "2", "3"])

	def test_tuple_input_stringified(self):
		result = _to_list((1, 2, 3))
		self.assertEqual(result, ["1", "2", "3"])

	def test_set_input_stringified(self):
		result = _to_list({1, 2, 3})
		self.assertEqual(sorted(result), ["1", "2", "3"])

	def test_comma_separated_string_split_and_stripped(self):
		result = _to_list("a, b, c")
		self.assertEqual(result, ["a", "b", "c"])

	def test_comma_separated_string_with_extra_whitespace(self):
		result = _to_list("  x  ,  y  ,  z  ")
		self.assertEqual(result, ["x", "y", "z"])

	def test_comma_separated_string_empty_segments_dropped(self):
		result = _to_list("a,,b,,c")
		self.assertEqual(result, ["a", "b", "c"])

	def test_empty_string_returns_empty_list(self):
		result = _to_list("")
		self.assertEqual(result, [])

	def test_single_value_string(self):
		result = _to_list("single")
		self.assertEqual(result, ["single"])


class TestFiltersToQueryParams(unittest.TestCase):
	def test_equals_operator_camel_cased(self):
		filters = [["", "user_name", "=", "john"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("userName", parsed)
		self.assertEqual(parsed["userName"][0], "john")

	def test_double_equals_operator(self):
		filters = [["", "status", "==", "active"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("status", parsed)
		self.assertEqual(parsed["status"][0], "active")

	def test_wrong_length_tuple_skipped(self):
		filters = [["", "field"], ["", "field", "="], ["", "field", "=", "val", "extra"]]
		result = filters_to_query_params(filters)
		self.assertEqual(result, "")

	def test_like_operator_strips_percent_and_underscore(self):
		filters = [["", "description", "like", "%test%_value_%"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertEqual(parsed["description"][0], "testvalue")

	def test_in_operator_with_list_comma_joined(self):
		filters = [["", "status", "in", ["active", "pending", "done"]]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertEqual(parsed["status"][0], "active,pending,done")

	def test_in_operator_with_empty_list_omitted(self):
		filters = [["", "status", "in", []]]
		result = filters_to_query_params(filters)
		self.assertEqual(result, "")

	def test_in_operator_with_comma_string_value(self):
		filters = [["", "tags", "in", "tag1, tag2, tag3"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertEqual(parsed["tags"][0], "tag1,tag2,tag3")

	def test_not_in_operator_with_list(self):
		filters = [["", "status", "not in", ["archived", "deleted"]]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertEqual(parsed["status"][0], "archived,deleted")

	def test_gte_operator_suffix(self):
		filters = [["", "created_date", ">=", "2024-01-01"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("createdDateGte", parsed)
		self.assertEqual(parsed["createdDateGte"][0], "2024-01-01")

	def test_gt_operator_suffix(self):
		filters = [["", "price", ">", "100"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("priceGt", parsed)
		self.assertEqual(parsed["priceGt"][0], "100")

	def test_lte_operator_suffix(self):
		filters = [["", "modified_date", "<=", "2024-12-31"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("modifiedDateLte", parsed)
		self.assertEqual(parsed["modifiedDateLte"][0], "2024-12-31")

	def test_lt_operator_suffix(self):
		filters = [["", "quantity", "<", "50"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("quantityLt", parsed)
		self.assertEqual(parsed["quantityLt"][0], "50")

	def test_between_operator_with_valid_tuple(self):
		filters = [["", "age", "between", (18, 65)]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("ageStart", parsed)
		self.assertIn("ageEnd", parsed)
		self.assertEqual(parsed["ageStart"][0], "18")
		self.assertEqual(parsed["ageEnd"][0], "65")

	def test_between_operator_with_list_value(self):
		filters = [["", "price", "between", [10, 100]]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertEqual(parsed["priceStart"][0], "10")
		self.assertEqual(parsed["priceEnd"][0], "100")

	def test_between_operator_malformed_value_silently_skipped(self):
		filters = [["", "range", "between", "not_a_tuple"]]
		result = filters_to_query_params(filters)
		self.assertEqual(result, "")

	def test_between_operator_single_value_silently_skipped(self):
		filters = [["", "range", "between", [42]]]
		result = filters_to_query_params(filters)
		self.assertEqual(result, "")

	def test_none_operator_treated_as_empty_string(self):
		filters = [["", "field", None, "value"]]
		result = filters_to_query_params(filters)
		self.assertEqual(result, "")

	def test_empty_string_operator_treated_as_empty_string(self):
		filters = [["", "field", "", "value"]]
		result = filters_to_query_params(filters)
		self.assertEqual(result, "")

	def test_empty_filters_list_returns_empty_string(self):
		result = filters_to_query_params([])
		self.assertEqual(result, "")

	def test_none_filters_returns_empty_string(self):
		result = filters_to_query_params(None)
		self.assertEqual(result, "")

	def test_multiple_filters_combined(self):
		filters = [
			["", "status", "=", "active"],
			["", "age", ">=", "18"],
			["", "tags", "in", ["a", "b"]],
		]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertEqual(parsed["status"][0], "active")
		self.assertEqual(parsed["ageGte"][0], "18")
		self.assertEqual(parsed["tags"][0], "a,b")

	def test_operator_case_insensitive(self):
		filters = [["", "field", "LIKE", "%test%"]]
		result = filters_to_query_params(filters)
		parsed = parse_qs(result)
		self.assertIn("field", parsed)
		self.assertEqual(parsed["field"][0], "test")


class TestReplaceMachineIdWithName(unittest.TestCase):
	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_machine_id_field_replaced_with_name(self, mock_get_name):
		mock_get_name.return_value = "Machine-001"
		filters = [["", "machine_id", "=", "mach_123"]]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0][1], "machine_name")
		self.assertEqual(result[0][3], "Machine-001")
		mock_get_name.assert_called_once_with("mach_123")

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_machine_id_field_returns_none_original_passed_through(self, mock_get_name):
		mock_get_name.return_value = None
		filters = [["", "machine_id", "=", "mach_999"]]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0], filters[0])
		mock_get_name.assert_called_once_with("mach_999")

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_machine_id_field_returns_empty_string_original_passed_through(self, mock_get_name):
		mock_get_name.return_value = ""
		filters = [["", "machine_id", "=", "mach_999"]]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(result[0], filters[0])

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_different_field_name_not_replaced(self, mock_get_name):
		filters = [["", "machine_name", "=", "Machine-001"]]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(result[0], filters[0])
		mock_get_name.assert_not_called()

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_non_list_tuple_filter_passed_through(self, mock_get_name):
		filters = ["not_a_tuple"]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(result[0], "not_a_tuple")
		mock_get_name.assert_not_called()

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_filter_shorter_than_4_elements_passed_through(self, mock_get_name):
		filters = [["", "machine_id", "="]]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(result[0], filters[0])
		mock_get_name.assert_not_called()

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_empty_filters_returns_empty_list(self, mock_get_name):
		result = replace_machine_id_with_name([])
		self.assertEqual(result, [])
		mock_get_name.assert_not_called()

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_none_filters_returns_empty_list(self, mock_get_name):
		result = replace_machine_id_with_name(None)
		self.assertEqual(result, [])
		mock_get_name.assert_not_called()

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_multiple_filters_mixed(self, mock_get_name):
		mock_get_name.side_effect = ["Machine-A", None]
		filters = [
			["", "machine_id", "=", "id_1"],
			["", "status", "=", "active"],
			["", "machine_id", "=", "id_2"],
		]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(len(result), 3)
		self.assertEqual(result[0][1], "machine_name")
		self.assertEqual(result[0][3], "Machine-A")
		self.assertEqual(result[1], filters[1])
		self.assertEqual(result[2][1], "machine_id")
		self.assertEqual(result[2][3], "id_2")

	@patch("ivm.machine_hardware_management.utils.filter_utils.get_machine_name_from_machine_id")
	def test_preserves_other_tuple_elements(self, mock_get_name):
		mock_get_name.return_value = "Machine-X"
		filters = [["custom_doctype", "machine_id", "like", "mach_123"]]
		result = replace_machine_id_with_name(filters)
		self.assertEqual(result[0][0], "custom_doctype")
		self.assertEqual(result[0][2], "like")


class TestFrappeFiltersToDict(unittest.TestCase):
	def test_equals_operator_basic(self):
		filters = [["", "status", "=", "active"]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result["status"], "active")

	def test_double_equals_operator(self):
		filters = [["", "status", "==", "active"]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result["status"], "active")

	def test_wrong_length_tuple_skipped(self):
		filters = [["", "field"], ["", "field", "="], ["", "field", "=", "val", "extra"]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result, {})

	def test_like_operator_strips_percent_and_underscore(self):
		filters = [["", "description", "like", "%test%_value_%"]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result["description"], "testvalue")

	def test_in_operator_with_list_comma_joined(self):
		filters = [["", "status", "in", ["active", "pending"]]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result["status"], "active,pending")

	def test_in_operator_with_empty_list_omitted(self):
		filters = [["", "status", "in", []]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result, {})

	def test_not_in_operator_with_list(self):
		filters = [["", "status", "not in", ["archived"]]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result["status"], "archived")

	def test_gte_operator_suffix(self):
		filters = [["", "created_date", ">=", "2024-01-01"]]
		result = frappe_filters_to_dict(filters)
		self.assertIn("createdDateGte", result)
		self.assertEqual(result["createdDateGte"], "2024-01-01")

	def test_gt_operator_suffix(self):
		filters = [["", "price", ">", "100"]]
		result = frappe_filters_to_dict(filters)
		self.assertIn("priceGt", result)
		self.assertEqual(result["priceGt"], "100")

	def test_lte_operator_suffix(self):
		filters = [["", "modified_date", "<=", "2024-12-31"]]
		result = frappe_filters_to_dict(filters)
		self.assertIn("modifiedDateLte", result)
		self.assertEqual(result["modifiedDateLte"], "2024-12-31")

	def test_lt_operator_suffix(self):
		filters = [["", "quantity", "<", "50"]]
		result = frappe_filters_to_dict(filters)
		self.assertIn("quantityLt", result)
		self.assertEqual(result["quantityLt"], "50")

	def test_between_operator_with_valid_tuple(self):
		filters = [["", "age", "between", (18, 65)]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result["ageStart"], 18)
		self.assertEqual(result["ageEnd"], 65)

	def test_between_operator_malformed_value_silently_skipped(self):
		filters = [["", "range", "between", "not_a_tuple"]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result, {})

	def test_none_operator_treated_as_empty_string(self):
		filters = [["", "field", None, "value"]]
		result = frappe_filters_to_dict(filters)
		self.assertEqual(result, {})

	def test_empty_filters_list_returns_empty_dict(self):
		result = frappe_filters_to_dict([])
		self.assertEqual(result, {})

	def test_none_filters_returns_empty_dict(self):
		result = frappe_filters_to_dict(None)
		self.assertEqual(result, {})

	def test_default_field_map_creation_to_created_date(self):
		filters = [["", "creation", "=", "2024-01-01"]]
		result = frappe_filters_to_dict(filters)
		self.assertIn("createdDate", result)
		self.assertEqual(result["createdDate"], "2024-01-01")

	def test_default_field_map_modified_to_modified_date(self):
		filters = [["", "modified", "=", "2024-01-01"]]
		result = frappe_filters_to_dict(filters)
		self.assertIn("modifiedDate", result)
		self.assertEqual(result["modifiedDate"], "2024-01-01")

	def test_custom_field_map_overrides_default(self):
		filters = [["", "creation", "=", "2024-01-01"]]
		custom_map = {"creation": "customCreatedField"}
		result = frappe_filters_to_dict(filters, field_map=custom_map)
		self.assertIn("customCreatedField", result)
		self.assertNotIn("createdDate", result)

	def test_custom_field_map_new_field(self):
		filters = [["", "custom_field", "=", "value"]]
		custom_map = {"custom_field": "mappedField"}
		result = frappe_filters_to_dict(filters, field_map=custom_map)
		self.assertIn("mappedField", result)
		self.assertEqual(result["mappedField"], "value")

	def test_field_map_none_uses_default_only(self):
		filters = [["", "creation", "=", "2024-01-01"]]
		result = frappe_filters_to_dict(filters, field_map=None)
		self.assertIn("createdDate", result)

	def test_multiple_filters_with_field_map(self):
		filters = [
			["", "creation", "=", "2024-01-01"],
			["", "status", "=", "active"],
		]
		custom_map = {"status": "statusCode"}
		result = frappe_filters_to_dict(filters, field_map=custom_map)
		self.assertIn("createdDate", result)
		self.assertIn("statusCode", result)
		self.assertEqual(result["createdDate"], "2024-01-01")
		self.assertEqual(result["statusCode"], "active")


class TestFrappeSortToDict(unittest.TestCase):
	def test_none_order_by_returns_empty_dict(self):
		result = frappe_sort_to_dict(None)
		self.assertEqual(result, {})

	def test_empty_string_order_by_returns_empty_dict(self):
		result = frappe_sort_to_dict("")
		self.assertEqual(result, {})

	def test_simple_field_asc_default(self):
		result = frappe_sort_to_dict("status")
		self.assertEqual(result["sortField"], "status")
		self.assertEqual(result["sortOrder"], "asc")

	def test_simple_field_with_asc_direction(self):
		result = frappe_sort_to_dict("status asc")
		self.assertEqual(result["sortField"], "status")
		self.assertEqual(result["sortOrder"], "asc")

	def test_simple_field_with_desc_direction(self):
		result = frappe_sort_to_dict("status desc")
		self.assertEqual(result["sortField"], "status")
		self.assertEqual(result["sortOrder"], "desc")

	def test_backtick_quoted_field_simple(self):
		result = frappe_sort_to_dict("`status`")
		self.assertEqual(result["sortField"], "status")
		self.assertEqual(result["sortOrder"], "asc")

	def test_backtick_quoted_field_with_direction(self):
		result = frappe_sort_to_dict("`status` desc")
		self.assertEqual(result["sortField"], "status")
		self.assertEqual(result["sortOrder"], "desc")

	def test_table_prefix_with_backticks(self):
		result = frappe_sort_to_dict("`tabMachine`.`creation` desc")
		self.assertEqual(result["sortField"], "createdDate")
		self.assertEqual(result["sortOrder"], "desc")

	def test_table_prefix_without_backticks_regex_captures_full_dotted_name(self):
		result = frappe_sort_to_dict("tabMachine.creation asc")
		self.assertEqual(result["sortField"], "tabMachine.creation")
		self.assertEqual(result["sortOrder"], "asc")

	def test_modified_field_mapped_via_default_field_map(self):
		result = frappe_sort_to_dict("modified desc")
		self.assertEqual(result["sortField"], "modifiedDate")
		self.assertEqual(result["sortOrder"], "desc")

	def test_creation_field_mapped_via_default_field_map(self):
		result = frappe_sort_to_dict("creation asc")
		self.assertEqual(result["sortField"], "createdDate")
		self.assertEqual(result["sortOrder"], "asc")

	def test_custom_field_map_overrides_default(self):
		custom_map = {"creation": "customCreatedField"}
		result = frappe_sort_to_dict("creation desc", field_map=custom_map)
		self.assertEqual(result["sortField"], "customCreatedField")
		self.assertEqual(result["sortOrder"], "desc")

	def test_custom_field_map_new_field(self):
		custom_map = {"custom_field": "mappedField"}
		result = frappe_sort_to_dict("custom_field asc", field_map=custom_map)
		self.assertEqual(result["sortField"], "mappedField")
		self.assertEqual(result["sortOrder"], "asc")

	def test_camel_case_conversion(self):
		result = frappe_sort_to_dict("user_name asc")
		self.assertEqual(result["sortField"], "userName")
		self.assertEqual(result["sortOrder"], "asc")

	def test_invalid_direction_defaults_to_asc(self):
		result = frappe_sort_to_dict("status invalid")
		self.assertEqual(result["sortField"], "status")
		self.assertEqual(result["sortOrder"], "asc")

	def test_direction_case_insensitive(self):
		result = frappe_sort_to_dict("status DESC")
		self.assertEqual(result["sortOrder"], "desc")

	def test_direction_case_insensitive_asc(self):
		result = frappe_sort_to_dict("status ASC")
		self.assertEqual(result["sortOrder"], "asc")

	def test_field_map_none_uses_default_only(self):
		result = frappe_sort_to_dict("creation asc", field_map=None)
		self.assertEqual(result["sortField"], "createdDate")

	def test_backtick_quoted_field_with_table_prefix_and_direction(self):
		result = frappe_sort_to_dict("`tabItem`.`item_name` asc")
		self.assertEqual(result["sortField"], "itemName")
		self.assertEqual(result["sortOrder"], "asc")

	def test_multiple_dots_in_field_regex_captures_full_dotted_name(self):
		result = frappe_sort_to_dict("schema.table.field desc")
		self.assertEqual(result["sortField"], "schema.table.field")
		self.assertEqual(result["sortOrder"], "desc")
