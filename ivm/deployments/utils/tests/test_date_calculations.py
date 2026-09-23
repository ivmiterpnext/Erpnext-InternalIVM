"""Integration tests for ivm.deployments.utils.date_calculations"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite
from frappe.utils import getdate

from ivm.deployments.utils.date_calculations import add_business_days


class TestAddBusinessDays(ERPNextTestSuite):
	"""Test add_business_days primitive."""

	def test_zero_days_returns_start_date_unchanged(self):
		"""business_days=0 returns start_date unchanged."""
		start = getdate("2024-01-01")  # Monday
		result = add_business_days(start, 0)
		self.assertEqual(getdate(result), start)

	def test_all_weekdays_plus_one_business_day(self):
		"""For each ISO weekday, add_business_days(date, 1) lands on next weekday."""
		# 2024-01-01 is Monday; use 7 consecutive dates (one per weekday)
		base_dates = [
			("2024-01-01", "2024-01-02"),  # Mon -> Tue
			("2024-01-02", "2024-01-03"),  # Tue -> Wed
			("2024-01-03", "2024-01-04"),  # Wed -> Thu
			("2024-01-04", "2024-01-05"),  # Thu -> Fri
			("2024-01-05", "2024-01-08"),  # Fri -> Mon (skip weekend)
			("2024-01-06", "2024-01-08"),  # Sat -> Mon (skip weekend)
			("2024-01-07", "2024-01-08"),  # Sun -> Mon (skip weekend)
		]
		for start_str, expected_str in base_dates:
			with self.subTest(start=start_str):
				result = add_business_days(start_str, 1)
				self.assertEqual(getdate(result), getdate(expected_str))

	def test_all_weekdays_plus_five_business_days(self):
		"""For each ISO weekday, add_business_days(date, 5) produces correct result."""
		# 5 business days = 1 full week (Mon-Fri)
		base_dates = [
			("2024-01-01", "2024-01-08"),  # Mon + 5 = Mon (next week)
			("2024-01-02", "2024-01-09"),  # Tue + 5 = Tue (next week)
			("2024-01-03", "2024-01-10"),  # Wed + 5 = Wed (next week)
			("2024-01-04", "2024-01-11"),  # Thu + 5 = Thu (next week)
			("2024-01-05", "2024-01-12"),  # Fri + 5 = Fri (next week)
			("2024-01-06", "2024-01-12"),  # Sat + 5 = Fri (next week)
			("2024-01-07", "2024-01-12"),  # Sun + 5 = Fri (next week)
		]
		for start_str, expected_str in base_dates:
			with self.subTest(start=start_str):
				result = add_business_days(start_str, 5)
				self.assertEqual(getdate(result), getdate(expected_str))

	def test_all_weekdays_plus_ten_business_days(self):
		"""For each ISO weekday, add_business_days(date, 10) produces correct result."""
		# 10 business days = 2 full weeks
		base_dates = [
			("2024-01-01", "2024-01-15"),  # Mon + 10 = Mon (2 weeks later)
			("2024-01-02", "2024-01-16"),  # Tue + 10 = Tue (2 weeks later)
			("2024-01-03", "2024-01-17"),  # Wed + 10 = Wed (2 weeks later)
			("2024-01-04", "2024-01-18"),  # Thu + 10 = Thu (2 weeks later)
			("2024-01-05", "2024-01-19"),  # Fri + 10 = Fri (2 weeks later)
			("2024-01-06", "2024-01-19"),  # Sat + 10 = Fri (2 weeks later)
			("2024-01-07", "2024-01-19"),  # Sun + 10 = Fri (2 weeks later)
		]
		for start_str, expected_str in base_dates:
			with self.subTest(start=start_str):
				result = add_business_days(start_str, 10)
				self.assertEqual(getdate(result), getdate(expected_str))

	def test_result_always_weekday(self):
		"""Result of add_business_days always has weekday() < 5 (Mon-Fri)."""
		test_cases = [
			("2024-01-01", 1),
			("2024-01-01", 5),
			("2024-01-01", 10),
			("2024-01-06", 1),  # Saturday
			("2024-01-07", 1),  # Sunday
		]
		for start_str, days in test_cases:
			with self.subTest(start=start_str, days=days):
				result = add_business_days(start_str, days)
				self.assertLess(getdate(result).weekday(), 5)

	def test_negative_business_days_steps_backward(self):
		"""Negative business_days steps backward and lands on weekday."""
		# 2024-01-08 is Monday; -3 business days should land on Wed 2024-01-03
		# (Mon back 1 = Fri, back 2 = Thu, back 3 = Wed)
		result = add_business_days("2024-01-08", -3)
		self.assertEqual(getdate(result), getdate("2024-01-03"))
		self.assertLess(getdate(result).weekday(), 5)

	def test_exact_multiple_of_five_from_monday(self):
		"""business_days=5,10,15 from Monday lands exactly N weeks later."""
		monday = getdate("2024-01-01")
		for weeks in [1, 2, 3]:
			with self.subTest(weeks=weeks):
				result = add_business_days(monday, weeks * 5)
				expected = monday + timedelta(days=weeks * 7)
				self.assertEqual(getdate(result), expected)
