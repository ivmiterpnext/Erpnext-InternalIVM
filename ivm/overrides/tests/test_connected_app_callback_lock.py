"""Tests for ivm.overrides.connected_app_callback_lock.callback."""

import unittest
from unittest.mock import MagicMock, patch

from ivm.overrides.connected_app_callback_lock import callback as _callback_patched


class TestCallbackPatched(unittest.TestCase):
	"""Test cases for _callback_patched()."""

	def test_update_data_is_wrapped_in_filelock(self):
		"""The token write inside the patched callback acquires the per-token-cache
		filelock before calling update_data()."""
		fake_session = MagicMock()
		fake_session.user = "user@example.com"
		fake_request = MagicMock()
		fake_request.path = (
			"/api/method/frappe.integrations.doctype.connected_app.connected_app.callback/test-app"
		)

		connected_app = MagicMock()
		connected_app.name = "test-app"
		connected_app.get_oauth2_session.return_value.fetch_token.return_value = {
			"access_token": "x",
			"expires_in": 3600,
		}
		connected_app.get_query_params.return_value = {}
		connected_app.get_url.return_value = "https://example.com"

		token_cache = MagicMock()
		token_cache.name = "test-app-user@example.com"
		token_cache.state = "expected-state"
		token_cache.get.return_value = None

		class _NullContext:
			def __enter__(self):
				return self

			def __exit__(self, *args):
				return False

		# new= avoids mock inspecting frappe's Local proxies (which raises AttributeError: __class__)
		with (
			patch("frappe.local", new=MagicMock()),
			patch("frappe.session", new=fake_session),
			patch("frappe.request", new=fake_request),
		):
			with patch("frappe.get_doc", side_effect=[connected_app, token_cache]):
				with patch(
					"ivm.overrides.connected_app_callback_lock.filelock",
					side_effect=lambda name: _NullContext(),
				) as mock_filelock:
					_callback_patched(code="abc", state="expected-state")

		mock_filelock.assert_called_once_with(f"token_cache_{token_cache.name}")
		token_cache.update_data.assert_called_once()


if __name__ == "__main__":
	unittest.main()
