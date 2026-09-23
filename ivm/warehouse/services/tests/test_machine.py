"""Integration tests for ivm.warehouse.services.machine"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.warehouse.services.machine import apply_machine_data, fetch_machine

_ICORP_GET_TARGET = "ivm.warehouse.services.machine.icorp_api_get"


class TestFetchMachine(ERPNextTestSuite):
	def test_returns_none_when_not_found(self):
		with patch(_ICORP_GET_TARGET, return_value={"data": []}):
			self.assertIsNone(fetch_machine("M1", "CLIENT1"))

	def test_returns_none_when_response_not_dict(self):
		with patch(_ICORP_GET_TARGET, return_value=None):
			self.assertIsNone(fetch_machine("M1", "CLIENT1"))

	def test_returns_mapped_fields_on_success(self):
		api_response = {"data": [{"id": 42, "serial_number": "SN-1", "board_serial_number": "PN-1"}]}
		with patch(_ICORP_GET_TARGET, return_value=api_response):
			result = fetch_machine("M1", "CLIENT1")
		self.assertEqual(
			result,
			{
				"icorp_machine_id": 42,
				"serial_number": "SN-1",
				"prose_number": "PN-1",
			},
		)

	def test_exception_from_api_returns_none(self):
		with patch(_ICORP_GET_TARGET, side_effect=Exception("boom")):
			self.assertIsNone(fetch_machine("M1", "CLIENT1"))


class TestApplyMachineData(ERPNextTestSuite):
	def test_sets_truthy_fields_only(self):
		wr = frappe._dict(icorp_machine_id=None, serial_number=None, prose_number=None)
		apply_machine_data(wr, {"icorp_machine_id": 7, "serial_number": None, "prose_number": "PN-9"})
		self.assertEqual(wr.icorp_machine_id, 7)
		self.assertIsNone(wr.serial_number)
		self.assertEqual(wr.prose_number, "PN-9")

	def test_missing_keys_leave_fields_untouched(self):
		wr = frappe._dict(icorp_machine_id="EXISTING")
		apply_machine_data(wr, {})
		self.assertEqual(wr.icorp_machine_id, "EXISTING")
