"""Tests for ivm.support.event_handlers.communication header sanitization helpers."""

import unittest
from email.utils import getaddresses
from unittest.mock import MagicMock

from ivm.support.event_handlers.communication import (
	_strip_stray_quotes,
	_unfold_header_whitespace,
	sanitize_email_header_fields,
)

TRACEBACK_STRING = (
	'"Gajjar, Mayur" <mayur.gajjar@intel.com>, "Support@ivminc.com"\n\t<Support@ivminc.com>, '
	'"Adkins, GeraldX" <geraldx.adkins@intel.com>, "Danielle\n Lanteigne" <d_lanteigne@ivminc.com>'
)


def _clean(value):
	return _strip_stray_quotes(_unfold_header_whitespace(value))


class TestCommunicationSanitization(unittest.TestCase):
	"""Test cases for header unfolding and sanitization."""

	def test_unfolds_newline_space_in_quoted_display_name(self):
		"""Newline+space inside quoted display name is collapsed before parsing."""
		result = _clean('"Danielle\n Lanteigne" <d_lanteigne@ivminc.com>')
		self.assertEqual(
			getaddresses([result]),
			[("Danielle Lanteigne", "d_lanteigne@ivminc.com")],
		)

	def test_unfolds_newline_tab_before_angle_bracket(self):
		"""Newline+tab between quoted name and angle-bracket address is collapsed."""
		result = _clean('"Support@ivminc.com"\n\t<Support@ivminc.com>')
		addresses = [addr for _, addr in getaddresses([result])]
		self.assertEqual(addresses, ["Support@ivminc.com"])

	def test_full_reproduction_of_traceback_string(self):
		"""Full failing cc string recovers all 4 addresses after sanitization."""
		doc = MagicMock()
		doc.get.side_effect = lambda field: TRACEBACK_STRING if field == "cc" else None

		sanitize_email_header_fields(doc, None)

		doc.set.assert_called_once()
		field, value = doc.set.call_args[0]
		self.assertEqual(field, "cc")
		addresses = [addr for _, addr in getaddresses([value])]
		self.assertEqual(len(addresses), 4)
		self.assertIn("d_lanteigne@ivminc.com", addresses)

	def test_existing_stray_quote_stripping_still_works(self):
		"""Lone unmatched quote is stripped; well-formed quoted pair is preserved."""
		result = _strip_stray_quotes('"Bad Name <bad@example.com>, "Good Name" <good@example.com>')
		self.assertEqual(result, 'Bad Name <bad@example.com>, "Good Name" <good@example.com>')
		self.assertNotIn('"Bad', result)
		self.assertIn('"Good Name" <good@example.com>', result)

	def test_hook_sets_doc_fields_for_all_three_when_present(self):
		"""Hook sets every non-empty field and skips None fields."""
		values = {
			"recipients": "a@example.com",
			"cc": '"Danielle\n Lanteigne" <d_lanteigne@ivminc.com>',
			"bcc": None,
		}
		doc = MagicMock()
		doc.get.side_effect = lambda field: values.get(field)

		sanitize_email_header_fields(doc, None)

		set_fields = [call[0][0] for call in doc.set.call_args_list]
		self.assertIn("recipients", set_fields)
		self.assertIn("cc", set_fields)
		self.assertNotIn("bcc", set_fields)

		cc_value = next(call[0][1] for call in doc.set.call_args_list if call[0][0] == "cc")
		self.assertNotIn("\n", cc_value)
		self.assertEqual(cc_value, '"Danielle Lanteigne" <d_lanteigne@ivminc.com>')

		recipients_value = next(call[0][1] for call in doc.set.call_args_list if call[0][0] == "recipients")
		self.assertEqual(recipients_value, "a@example.com")

	def test_idempotent_on_already_clean_input(self):
		"""Applying the sanitizers twice yields the same result as once."""
		clean = '"Gajjar, Mayur" <mayur.gajjar@intel.com>, "Support@ivminc.com" <Support@ivminc.com>'
		once = _clean(clean)
		twice = _clean(once)
		self.assertEqual(once, twice)
		self.assertEqual(once, clean)
