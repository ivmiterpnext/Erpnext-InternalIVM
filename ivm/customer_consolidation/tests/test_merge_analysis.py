"""Tests for ivm.customer_consolidation.merge_analysis (pure functions only)"""

from erpnext.tests.utils import ERPNextTestSuite

from ivm.customer_consolidation.merge_analysis import (
	diff_customer_values,
	find_possible_duplicate_addresses,
	find_possible_duplicate_contacts,
	find_unresolved_field_conflicts,
)


class TestFindPossibleDuplicateContacts(ERPNextTestSuite):
	"""find_possible_duplicate_contacts"""

	def test_same_email_flagged(self):
		a = [{"name": "C1", "first_name": "Jane", "last_name": "Doe", "email_id": "jane@example.com"}]
		b = [{"name": "C2", "first_name": "J.", "last_name": "D.", "email_id": "JANE@example.com"}]
		self.assertEqual(find_possible_duplicate_contacts(a, b), ["C1 <-> C2"])

	def test_same_normalized_full_name_flagged(self):
		a = [{"name": "C1", "first_name": "Jane", "last_name": "Doe", "email_id": ""}]
		b = [{"name": "C2", "first_name": "jane", "last_name": "doe", "email_id": ""}]
		self.assertEqual(find_possible_duplicate_contacts(a, b), ["C1 <-> C2"])

	def test_guillame_bourgeois_variant_flagged(self):
		a = [{"name": "C1", "first_name": "Guillame", "last_name": "Bourgeois-Pin", "email_id": ""}]
		b = [{"name": "C2", "first_name": "Guillamume", "last_name": "Bourgeois", "email_id": ""}]
		self.assertEqual(find_possible_duplicate_contacts(a, b), ["C1 <-> C2"])

	def test_clearly_different_people_not_flagged(self):
		a = [{"name": "C1", "first_name": "John", "last_name": "Smith", "email_id": ""}]
		b = [{"name": "C2", "first_name": "Jane", "last_name": "Doe", "email_id": ""}]
		self.assertEqual(find_possible_duplicate_contacts(a, b), [])


class TestFindPossibleDuplicateAddresses(ERPNextTestSuite):
	"""find_possible_duplicate_addresses"""

	def test_same_address_different_casing_flagged(self):
		a = [{"name": "A1", "address_line1": "175 WYMAN STREET", "city": "Waltham"}]
		b = [{"name": "A2", "address_line1": "175 Wyman Street", "city": "WALTHAM"}]
		self.assertEqual(find_possible_duplicate_addresses(a, b), ["A1 <-> A2"])

	def test_different_line1_not_flagged(self):
		a = [{"name": "A1", "address_line1": "175 Wyman Street", "city": "Waltham"}]
		b = [{"name": "A2", "address_line1": "1 Main Street", "city": "Waltham"}]
		self.assertEqual(find_possible_duplicate_addresses(a, b), [])


class TestDiffCustomerValues(ERPNextTestSuite):
	"""diff_customer_values"""

	def test_from_only_value_goes_to_copy_not_conflict(self):
		"""Losing side has data, surviving side has none - safe to auto-copy, not a conflict."""
		result = diff_customer_values({"website": "a.com"}, {"website": ""}, {"website": "Data"})
		self.assertEqual(result["fields_to_copy"], ["website: 'a.com'"])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_both_sides_different_real_values_is_a_conflict(self):
		result = diff_customer_values(
			{"account_owner": "afunk@ivminc.com"},
			{"account_owner": "rrex@ivminc.com"},
			{"account_owner": "Data"},
		)
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(len(result["fields_in_conflict"]), 1)
		self.assertIn("afunk@ivminc.com", result["fields_in_conflict"][0])
		self.assertIn("rrex@ivminc.com", result["fields_in_conflict"][0])

	def test_equal_values_not_reported(self):
		result = diff_customer_values({"website": "a.com"}, {"website": "a.com"}, {"website": "Data"})
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_empty_from_value_not_reported(self):
		result = diff_customer_values({"website": ""}, {"website": "b.com"}, {"website": "Data"})
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_unset_numeric_zero_not_a_conflict_or_copy(self):
		"""An Int/Float/Currency field sitting at its unset default of 0 isn't real data - not a
		conflict even if the other side has a real number, and not something to copy."""
		result = diff_customer_values(
			{"total_client_employees": "0"},
			{"total_client_employees": "16055"},
			{"total_client_employees": "Int"},
		)
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_real_numeric_value_only_on_losing_side_is_copied(self):
		result = diff_customer_values(
			{"total_client_employees": "500"},
			{"total_client_employees": "0"},
			{"total_client_employees": "Int"},
		)
		self.assertEqual(result["fields_to_copy"], ["total_client_employees: '500'"])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_numeric_text_stored_in_a_data_field_still_treats_zero_as_blank(self):
		"""The real-world case: fields like custom_total_account_sv are stored as Data, not Int,
		but still hold plain numeric text where 0 means unset. Both sides must parse as numbers
		for this rule to apply — it isn't fieldtype-dependent."""
		result = diff_customer_values(
			{"custom_total_account_sv": "0"},
			{"custom_total_account_sv": "19008"},
			{"custom_total_account_sv": "Data"},
		)
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_data_field_real_numeric_value_on_losing_side_copied_even_though_not_int_type(self):
		result = diff_customer_values(
			{"custom_total_account_sv": "12140"},
			{"custom_total_account_sv": "0"},
			{"custom_total_account_sv": "Data"},
		)
		self.assertEqual(result["fields_to_copy"], ["custom_total_account_sv: '12140'"])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_non_numeric_data_field_zero_string_is_not_treated_as_blank(self):
		"""If the other side isn't numeric-looking at all, a literal '0' stays a real value."""
		result = diff_customer_values({"code": "0"}, {"code": "abc"}, {"code": "Data"})
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(result["fields_in_conflict"], ["code: into='abc' vs from='0'"])

	def test_industry_difference_is_not_a_conflict(self):
		result = diff_customer_values({"industry": "Technology"}, {"industry": "Other"}, {"industry": "Link"})
		self.assertEqual(result["fields_to_copy"], [])
		self.assertEqual(result["fields_in_conflict"], [])

	def test_customer_primary_contact_difference_is_not_a_conflict(self):
		result = diff_customer_values(
			{"customer_primary_contact": "A-A"},
			{"customer_primary_contact": "B-B"},
			{"customer_primary_contact": "Data"},
		)
		self.assertNotIn("customer_primary_contact", str(result["fields_in_conflict"]))

	def test_industry_still_copied_when_survivor_side_is_blank(self):
		result = diff_customer_values({"industry": "Technology"}, {"industry": ""}, {"industry": "Link"})
		self.assertEqual(result["fields_to_copy"], ["industry: 'Technology'"])
		self.assertEqual(result["fields_in_conflict"], [])


class TestFindUnresolvedFieldConflicts(ERPNextTestSuite):
	"""find_unresolved_field_conflicts"""

	def test_conflict_with_no_resolution_is_unresolved(self):
		conflicts = ["account_owner: into='rrex@ivminc.com' vs from='afunk@ivminc.com'"]
		self.assertEqual(find_unresolved_field_conflicts(conflicts, {}), conflicts)

	def test_conflict_with_matching_resolution_is_resolved(self):
		conflicts = ["account_owner: into='rrex@ivminc.com' vs from='afunk@ivminc.com'"]
		resolutions = {"account_owner": "afunk@ivminc.com"}
		self.assertEqual(find_unresolved_field_conflicts(conflicts, resolutions), [])


class TestGetCustomerFieldTypes(ERPNextTestSuite):
	"""get_customer_field_types"""

	def test_disabled_is_never_compared(self):
		# A merge must never carry the loser's disabled flag onto the survivor (0 counts as blank
		# for numeric fields, so a disabled loser would otherwise show up in fields_to_copy).
		from ivm.customer_consolidation.merge_analysis import get_customer_field_types

		self.assertNotIn("disabled", get_customer_field_types())
