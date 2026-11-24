"""Tests for ivm.overrides.connected_app_token_refresh.CustomConnectedApp."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivm.overrides.connected_app_token_refresh import CustomConnectedApp


class TestConnectedAppTokenRefresh(unittest.TestCase):
	"""Test cases for CustomConnectedApp.get_active_token()."""

	def _make_app(self):
		app = CustomConnectedApp.__new__(CustomConnectedApp)
		app.name = "test-app"
		app.token_uri = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
		app.redirect_uri = "https://example.com/callback"
		return app

	def test_returns_cached_token_when_for_update_refetch_shows_not_expired(self):
		"""If the for_update=True re-fetch shows the token is no longer expired
		(e.g. another worker already refreshed it), no refresh/save is attempted."""
		app = self._make_app()
		stale_cache = MagicMock(name="stale_token_cache")
		stale_cache.name = "test-app-user@example.com"
		stale_cache.is_expired.return_value = True

		fresh_cache = MagicMock(name="fresh_token_cache")
		fresh_cache.is_expired.return_value = False

		with patch.object(app, "get_token_cache", return_value=stale_cache):
			with patch("frappe.utils.synchronization.filelock"):
				with patch("frappe.get_doc", return_value=fresh_cache) as mock_get_doc:
					result = app.get_active_token(user="user@example.com")

		mock_get_doc.assert_called_once_with("Token Cache", stale_cache.name, for_update=True)
		self.assertIs(result, fresh_cache)
		fresh_cache.update_data.assert_not_called()

	def test_refreshes_and_saves_when_for_update_refetch_still_expired(self):
		"""If the for_update=True re-fetch still shows expired, a refresh is
		fetched and saved via update_data()."""
		app = self._make_app()
		stale_cache = MagicMock(name="stale_token_cache")
		stale_cache.name = "test-app-user@example.com"
		stale_cache.is_expired.return_value = True

		fresh_cache = MagicMock(name="fresh_token_cache")
		fresh_cache.is_expired.return_value = True

		fake_token = {"access_token": "new-token", "expires_in": 3600}

		with patch.object(app, "get_token_cache", return_value=stale_cache):
			with patch.object(app, "_fetch_refreshed_token", return_value=fake_token) as mock_fetch:
				with patch("frappe.utils.synchronization.filelock"):
					with patch("frappe.get_doc", return_value=fresh_cache):
						result = app.get_active_token(user="user@example.com")

		mock_fetch.assert_called_once_with("user@example.com")
		fresh_cache.update_data.assert_called_once_with(fake_token)
		self.assertIs(result, fresh_cache)

	def test_retries_save_once_on_timestamp_mismatch(self):
		"""_save_token_with_retry re-fetches for_update=True and retries once
		if the first save() raises TimestampMismatchError."""
		app = self._make_app()
		first_cache = MagicMock(name="first_token_cache")
		first_cache.name = "test-app-user@example.com"
		first_cache.update_data.side_effect = frappe.TimestampMismatchError("stale")

		retried_cache = MagicMock(name="retried_token_cache")

		fake_token = {"access_token": "new-token", "expires_in": 3600}

		with patch("frappe.get_doc", return_value=retried_cache) as mock_get_doc:
			app._save_token_with_retry(first_cache, fake_token)

		mock_get_doc.assert_called_once_with("Token Cache", first_cache.name, for_update=True)
		retried_cache.update_data.assert_called_once_with(fake_token)

	def test_invalid_grant_enqueues_token_cache_deletion(self):
		"""An invalid_grant error during refresh enqueues delete_token_cache
		instead of propagating, and get_active_token returns None."""
		app = self._make_app()
		stale_cache = MagicMock(name="stale_token_cache")
		stale_cache.name = "test-app-user@example.com"
		stale_cache.modified = "2026-01-01 00:00:00"
		stale_cache.is_expired.return_value = True

		fresh_cache = MagicMock(name="fresh_token_cache")
		fresh_cache.name = "test-app-user@example.com"
		fresh_cache.modified = "2026-01-01 00:00:00"
		fresh_cache.is_expired.return_value = True

		with patch.object(app, "get_token_cache", return_value=stale_cache):
			with patch.object(app, "_fetch_refreshed_token", side_effect=Exception("invalid_grant")):
				with patch("frappe.utils.synchronization.filelock"):
					with patch("frappe.get_doc", return_value=fresh_cache):
						with patch("frappe.enqueue") as mock_enqueue:
							with patch.object(app, "log_error"):
								result = app.get_active_token(user="user@example.com")

		mock_enqueue.assert_called_once()
		self.assertIsNone(result)


if __name__ == "__main__":
	unittest.main()
