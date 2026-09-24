"""Tests for ivm.integrations.hubspot.api"""

from unittest.mock import MagicMock, patch

import requests
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.api import (
	_MAX_RETRIES,
	_RETRY_BACKOFF_SECONDS,
	HubSpotRateLimitExhausted,
	_download,
	_get_api_key,
	_get_client_secret,
	_get_portal_id,
	_retry_loop,
	download_file,
	get_deal_company_ids_by_role,
	get_deal_email_ids_batch,
	get_owner_email,
	verify_signature,
)


class TestRetryLoop(FrappeTestCase):
	"""_retry_loop core resilience logic"""

	def test_200_response_returns_response(self):
		"""200 response returns response immediately"""
		mock_response = MagicMock()
		mock_response.status_code = 200
		send = MagicMock(return_value=mock_response)

		result = _retry_loop(send)

		self.assertEqual(result, mock_response)
		send.assert_called_once_with(0)

	def test_429_with_retry_after_header_raises_with_clamped_seconds(self):
		"""429 with Retry-After header raises HubSpotRateLimitExhausted with clamped delay"""
		mock_response = MagicMock()
		mock_response.status_code = 429
		mock_response.headers = {"Retry-After": "5"}
		send = MagicMock(return_value=mock_response)

		with self.assertRaises(HubSpotRateLimitExhausted) as ctx:
			_retry_loop(send)

		self.assertEqual(ctx.exception.retry_after_seconds, 10.0)

	def test_429_with_retry_after_above_60_clamps_to_60(self):
		"""429 with Retry-After > 60 clamps to 60"""
		mock_response = MagicMock()
		mock_response.status_code = 429
		mock_response.headers = {"Retry-After": "120"}
		send = MagicMock(return_value=mock_response)

		with self.assertRaises(HubSpotRateLimitExhausted) as ctx:
			_retry_loop(send)

		self.assertEqual(ctx.exception.retry_after_seconds, 60.0)

	def test_429_without_retry_after_header_uses_default_10(self):
		"""429 without Retry-After header raises with default 10s"""
		mock_response = MagicMock()
		mock_response.status_code = 429
		mock_response.headers = {}
		send = MagicMock(return_value=mock_response)

		with self.assertRaises(HubSpotRateLimitExhausted) as ctx:
			_retry_loop(send)

		self.assertEqual(ctx.exception.retry_after_seconds, 10.0)

	def test_429_with_invalid_retry_after_uses_default(self):
		"""429 with non-numeric Retry-After uses default 10s"""
		mock_response = MagicMock()
		mock_response.status_code = 429
		mock_response.headers = {"Retry-After": "invalid"}
		send = MagicMock(return_value=mock_response)

		with self.assertRaises(HubSpotRateLimitExhausted) as ctx:
			_retry_loop(send)

		self.assertEqual(ctx.exception.retry_after_seconds, 10.0)

	def test_500_first_attempt_200_second_attempt_retries_and_succeeds(self):
		"""500 on first attempt, 200 on second attempt retries and succeeds"""
		mock_500 = MagicMock()
		mock_500.status_code = 500
		mock_200 = MagicMock()
		mock_200.status_code = 200
		send = MagicMock(side_effect=[mock_500, mock_200])

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			result = _retry_loop(send)

		self.assertEqual(result, mock_200)
		self.assertEqual(send.call_count, 2)

	def test_500_on_all_attempts_raises_after_max_retries(self):
		"""500 on all attempts raises HTTPError after _MAX_RETRIES"""
		mock_response = MagicMock()
		mock_response.status_code = 500
		mock_response.text = "Internal Server Error"
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
		send = MagicMock(return_value=mock_response)

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			with self.assertRaises(requests.exceptions.HTTPError) as ctx:
				_retry_loop(send)

		self.assertIn("Response body:", str(ctx.exception))
		self.assertEqual(send.call_count, _MAX_RETRIES)

	def test_502_503_504_also_retry(self):
		"""502, 503, 504 also trigger retry logic"""
		for status_code in [502, 503, 504]:
			mock_500 = MagicMock()
			mock_500.status_code = status_code
			mock_200 = MagicMock()
			mock_200.status_code = 200
			send = MagicMock(side_effect=[mock_500, mock_200])

			with patch("ivm.integrations.hubspot.api._server_error_backoff"):
				result = _retry_loop(send)

			self.assertEqual(result, mock_200)

	def test_request_exception_first_attempt_success_second_retries_and_succeeds(self):
		"""RequestException on first attempt, success on second retries and succeeds"""
		mock_200 = MagicMock()
		mock_200.status_code = 200
		send = MagicMock(side_effect=[requests.exceptions.ConnectionError("Connection failed"), mock_200])

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			result = _retry_loop(send)

		self.assertEqual(result, mock_200)
		self.assertEqual(send.call_count, 2)

	def test_request_exception_on_all_attempts_raises_after_max_retries(self):
		"""RequestException on all attempts raises after _MAX_RETRIES"""
		send = MagicMock(side_effect=requests.exceptions.ConnectionError("Connection failed"))

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			with self.assertRaises(requests.exceptions.ConnectionError):
				_retry_loop(send)

		self.assertEqual(send.call_count, _MAX_RETRIES)

	def test_400_retries_and_eventually_raises(self):
		"""400 retries (caught as RequestException) and raises after _MAX_RETRIES"""
		mock_response = MagicMock()
		mock_response.status_code = 400
		mock_response.text = "Bad Request"
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Client Error")
		send = MagicMock(return_value=mock_response)

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			with self.assertRaises(requests.exceptions.HTTPError):
				_retry_loop(send)

		self.assertEqual(send.call_count, _MAX_RETRIES)

	def test_403_retries_and_eventually_raises(self):
		"""403 retries (caught as RequestException) and raises after _MAX_RETRIES"""
		mock_response = MagicMock()
		mock_response.status_code = 403
		mock_response.text = "Forbidden"
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("403 Forbidden")
		send = MagicMock(return_value=mock_response)

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			with self.assertRaises(requests.exceptions.HTTPError):
				_retry_loop(send)

		self.assertEqual(send.call_count, _MAX_RETRIES)

	def test_404_retries_and_eventually_raises(self):
		"""404 retries (caught as RequestException) and raises after _MAX_RETRIES"""
		mock_response = MagicMock()
		mock_response.status_code = 404
		mock_response.text = "Not Found"
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
		send = MagicMock(return_value=mock_response)

		with patch("ivm.integrations.hubspot.api._server_error_backoff"):
			with self.assertRaises(requests.exceptions.HTTPError):
				_retry_loop(send)

		self.assertEqual(send.call_count, _MAX_RETRIES)


class TestVerifySignature(FrappeTestCase):
	"""verify_signature webhook validation"""

	def test_valid_signature_returns_true(self):
		"""Valid signature returns True"""
		with patch("ivm.integrations.hubspot.api._get_client_secret") as mock_secret:
			mock_secret.return_value = "test_secret"
			body = "test_body"
			import hashlib

			expected_hash = hashlib.sha256(b"test_secrettest_body").hexdigest()

			result = verify_signature(body, expected_hash)

			self.assertTrue(result)

	def test_invalid_signature_returns_false(self):
		"""Invalid signature returns False"""
		with patch("ivm.integrations.hubspot.api._get_client_secret") as mock_secret:
			mock_secret.return_value = "test_secret"
			body = "test_body"
			wrong_hash = "0" * 64

			result = verify_signature(body, wrong_hash)

			self.assertFalse(result)

	def test_empty_body_correct_hash_computed(self):
		"""Empty body computes correct hash"""
		with patch("ivm.integrations.hubspot.api._get_client_secret") as mock_secret:
			mock_secret.return_value = "secret"
			import hashlib

			expected_hash = hashlib.sha256(b"secret").hexdigest()

			result = verify_signature("", expected_hash)

			self.assertTrue(result)


class TestGetDealCompanyIdsByRole(FrappeTestCase):
	"""get_deal_company_ids_by_role association parsing"""

	def test_both_primary_and_master_labeled_associations(self):
		"""Response with both Primary and Master labeled associations returns correct tuple"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = [
				{"to_object_id": "100", "labels": ["Primary"]},
				{"to_object_id": "200", "labels": ["Master"]},
			]

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertEqual(primary, "100")
			self.assertEqual(master, "200")

	def test_only_primary_labeled_association(self):
		"""Response with only Primary returns (id, None)"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = [
				{"to_object_id": "100", "labels": ["Primary"]},
			]

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertEqual(primary, "100")
			self.assertIsNone(master)

	def test_only_master_labeled_association(self):
		"""Response with only Master returns (None, id)"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = [
				{"to_object_id": "200", "labels": ["Master"]},
			]

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertIsNone(primary)
			self.assertEqual(master, "200")

	def test_no_labeled_associations(self):
		"""Response with no labeled associations returns (None, None)"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = []

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertIsNone(primary)
			self.assertIsNone(master)

	def test_unlabeled_association_treated_as_primary(self):
		"""Unlabeled association treated as primary"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = [
				{"to_object_id": "100", "labels": []},
			]

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertEqual(primary, "100")
			self.assertIsNone(master)

	def test_multiple_primaries_first_one_wins(self):
		"""Multiple primaries in response, first one wins"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = [
				{"to_object_id": "100", "labels": []},
				{"to_object_id": "101", "labels": []},
			]

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertEqual(primary, "100")
			self.assertIsNone(master)

	def test_multiple_masters_first_one_wins(self):
		"""Multiple masters in response, first one wins"""
		with patch("ivm.integrations.hubspot.api.get_deal_company_associations") as mock_assoc:
			mock_assoc.return_value = [
				{"to_object_id": "200", "labels": ["Master"]},
				{"to_object_id": "201", "labels": ["Master"]},
			]

			primary, master = get_deal_company_ids_by_role("deal_123")

			self.assertIsNone(primary)
			self.assertEqual(master, "200")


class TestGetOwnerEmail(FrappeTestCase):
	"""get_owner_email with caching"""

	def test_valid_owner_returns_email(self):
		"""Valid owner returns email"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.return_value = {"email": "owner@example.com"}

			result = get_owner_email("owner_123")

			self.assertEqual(result, "owner@example.com")

	def test_call_twice_same_owner_api_called_once(self):
		"""Call twice with same owner_id, API called only once (lru_cache)"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.return_value = {"email": "owner@example.com"}

			get_owner_email.cache_clear()
			result1 = get_owner_email("owner_123")
			result2 = get_owner_email("owner_123")

			self.assertEqual(result1, "owner@example.com")
			self.assertEqual(result2, "owner@example.com")
			mock_get.assert_called_once()

	def test_api_error_returns_none_does_not_raise(self):
		"""API error returns None, does not raise"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.side_effect = requests.exceptions.RequestException("API error")

			result = get_owner_email("owner_123")

			self.assertIsNone(result)

	def test_missing_email_field_returns_none(self):
		"""Missing email field returns None"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.return_value = {"name": "Owner Name"}

			get_owner_email.cache_clear()
			result = get_owner_email("owner_missing_email")

			self.assertIsNone(result)

	def test_empty_email_field_returns_none(self):
		"""Empty email field returns None"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.return_value = {"email": ""}

			get_owner_email.cache_clear()
			result = get_owner_email("owner_empty_email")

			self.assertIsNone(result)


class TestDownloadFile(FrappeTestCase):
	"""download_file with metadata and content fetch"""

	def test_normal_flow_returns_filename_and_bytes(self):
		"""Normal flow returns (filename, bytes)"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			with patch("ivm.integrations.hubspot.api._download") as mock_download:
				mock_get.side_effect = [
					{"name": "document", "extension": "pdf"},
					{"url": "https://cdn.example.com/file.pdf?sig=xyz"},
				]
				mock_response = MagicMock()
				mock_response.content = b"PDF content here"
				mock_download.return_value = mock_response

				result = download_file("file_123")

				self.assertEqual(result, ("document.pdf", b"PDF content here"))

	def test_api_error_on_metadata_fetch_returns_none(self):
		"""API error on metadata fetch returns None"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.side_effect = requests.exceptions.RequestException("API error")

			result = download_file("file_123")

			self.assertIsNone(result)

	def test_api_error_on_content_download_returns_none(self):
		"""API error on content download returns None"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			with patch("ivm.integrations.hubspot.api._download") as mock_download:
				mock_get.side_effect = [
					{"name": "document", "extension": "pdf"},
					{"url": "https://cdn.example.com/file.pdf?sig=xyz"},
				]
				mock_download.side_effect = requests.exceptions.RequestException("Download failed")

				result = download_file("file_123")

				self.assertIsNone(result)

	def test_missing_signed_url_returns_none(self):
		"""Missing signed URL returns None"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			mock_get.side_effect = [
				{"name": "document", "extension": "pdf"},
				{"url": None},
			]

			result = download_file("file_123")

			self.assertIsNone(result)

	def test_filename_without_extension_adds_extension(self):
		"""Filename without extension adds extension from metadata"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			with patch("ivm.integrations.hubspot.api._download") as mock_download:
				mock_get.side_effect = [
					{"name": "document", "extension": "pdf"},
					{"url": "https://cdn.example.com/file.pdf?sig=xyz"},
				]
				mock_response = MagicMock()
				mock_response.content = b"PDF content"
				mock_download.return_value = mock_response

				result = download_file("file_123")

				self.assertEqual(result[0], "document.pdf")

	def test_filename_already_has_extension_not_duplicated(self):
		"""Filename already has extension, not duplicated"""
		with patch("ivm.integrations.hubspot.api._get") as mock_get:
			with patch("ivm.integrations.hubspot.api._download") as mock_download:
				mock_get.side_effect = [
					{"name": "document.pdf", "extension": "pdf"},
					{"url": "https://cdn.example.com/file.pdf?sig=xyz"},
				]
				mock_response = MagicMock()
				mock_response.content = b"PDF content"
				mock_download.return_value = mock_response

				result = download_file("file_123")

				self.assertEqual(result[0], "document.pdf")


class TestGetDealEmailIdsBatch(FrappeTestCase):
	"""get_deal_email_ids_batch with chunking"""

	def test_single_batch_less_than_100_deal_ids(self):
		"""Single batch (<100 deal ids) returns correct mapping"""
		with patch("ivm.integrations.hubspot.api._post") as mock_post:
			mock_post.return_value = {
				"results": [
					{
						"from": {"id": "deal_1"},
						"to": [
							{"toObjectId": "email_1"},
							{"toObjectId": "email_2"},
						],
					},
					{
						"from": {"id": "deal_2"},
						"to": [
							{"toObjectId": "email_3"},
						],
					},
				]
			}

			result = get_deal_email_ids_batch(["deal_1", "deal_2"])

			self.assertEqual(result["deal_1"], ["email_1", "email_2"])
			self.assertEqual(result["deal_2"], ["email_3"])
			mock_post.assert_called_once()

	def test_multi_batch_more_than_100_deal_ids(self):
		"""Multi-batch (>100 deal ids) chunks requests correctly and merges results"""
		with patch("ivm.integrations.hubspot.api._post") as mock_post:
			deal_ids = [f"deal_{i}" for i in range(150)]

			mock_post.side_effect = [
				{
					"results": [
						{"from": {"id": f"deal_{i}"}, "to": [{"toObjectId": f"email_{i}"}]}
						for i in range(100)
					]
				},
				{
					"results": [
						{"from": {"id": f"deal_{i}"}, "to": [{"toObjectId": f"email_{i}"}]}
						for i in range(100, 150)
					]
				},
			]

			result = get_deal_email_ids_batch(deal_ids)

			self.assertEqual(len(result), 150)
			self.assertEqual(result["deal_0"], ["email_0"])
			self.assertEqual(result["deal_149"], ["email_149"])
			self.assertEqual(mock_post.call_count, 2)

	def test_empty_response_returns_empty_dict(self):
		"""Empty response returns empty dict"""
		with patch("ivm.integrations.hubspot.api._post") as mock_post:
			mock_post.return_value = {"results": []}

			result = get_deal_email_ids_batch(["deal_1"])

			self.assertEqual(result, {"deal_1": []})

	def test_deal_with_no_emails_has_empty_list(self):
		"""Deal with no emails has empty list in result"""
		with patch("ivm.integrations.hubspot.api._post") as mock_post:
			mock_post.return_value = {
				"results": [
					{
						"from": {"id": "deal_1"},
						"to": [],
					},
				]
			}

			result = get_deal_email_ids_batch(["deal_1"])

			self.assertEqual(result["deal_1"], [])

	def test_empty_deal_ids_list_returns_empty_dict(self):
		"""Empty deal_ids list returns empty dict"""
		result = get_deal_email_ids_batch([])

		self.assertEqual(result, {})
