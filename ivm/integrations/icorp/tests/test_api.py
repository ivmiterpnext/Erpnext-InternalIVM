"""Tests for ivm.integrations.icorp.api"""

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from ivm.integrations.icorp.api import (
	extract_id,
	get_icorp_auth,
	icorp_api_delete,
	icorp_api_get,
	icorp_api_post,
	icorp_api_put,
	icorp_get_count,
)


class TestGetIcorpAuth(FrappeTestCase):
	"""get_icorp_auth function"""

	@patch("ivm.integrations.icorp.api.get_secrets")
	@patch("ivm.integrations.icorp.api._get_base_url")
	@patch("ivm.integrations.icorp.api._get_tenant_id")
	@patch("ivm.integrations.icorp.api._get_api_scope")
	@patch("ivm.integrations.icorp.api.requests.post")
	def test_successful_token_request(self, mock_post, mock_scope, mock_tenant, mock_base_url, mock_secrets):
		"""Successful token request returns (base_url, headers_with_bearer)"""
		mock_secrets.return_value = {
			"ICorpAPI-AzureAd-ClientId": "client_id",
			"ICorpAPI-AzureAd-ClientSecret": "client_secret",
			"FrappeServiceAccount-Username": "user",
			"FrappeServiceAccount-Password": "pass",
		}
		mock_tenant.return_value = "tenant_id"
		mock_scope.return_value = "scope"
		mock_base_url.return_value = "https://api.icorp.com"

		mock_response = MagicMock()
		mock_response.json.return_value = {"access_token": "test_token"}
		mock_post.return_value = mock_response

		base_url, headers = get_icorp_auth()

		self.assertEqual(base_url, "https://api.icorp.com")
		self.assertEqual(headers["Authorization"], "Bearer test_token")
		self.assertEqual(headers["Content-Type"], "application/json")

	@patch("ivm.integrations.icorp.api.get_secrets")
	@patch("ivm.integrations.icorp.api._get_base_url")
	@patch("ivm.integrations.icorp.api._get_tenant_id")
	@patch("ivm.integrations.icorp.api._get_api_scope")
	@patch("ivm.integrations.icorp.api.requests.post")
	def test_token_request_http_failure_raises(
		self, mock_post, mock_scope, mock_tenant, mock_base_url, mock_secrets
	):
		"""Token request HTTP failure raises"""
		mock_secrets.return_value = {
			"ICorpAPI-AzureAd-ClientId": "client_id",
			"ICorpAPI-AzureAd-ClientSecret": "client_secret",
			"FrappeServiceAccount-Username": "user",
			"FrappeServiceAccount-Password": "pass",
		}
		mock_tenant.return_value = "tenant_id"
		mock_scope.return_value = "scope"
		mock_base_url.return_value = "https://api.icorp.com"

		mock_response = MagicMock()
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("401 Unauthorized")
		mock_post.return_value = mock_response

		with self.assertRaises(requests.exceptions.HTTPError):
			get_icorp_auth()

	@patch("ivm.integrations.icorp.api._get_base_url")
	def test_missing_config_value_raises(self, mock_base_url):
		"""Missing config value raises frappe.throw"""
		mock_base_url.side_effect = frappe.ValidationError("icorp_api_base_url is not set")

		with self.assertRaises(frappe.ValidationError):
			get_icorp_auth()


class TestIcorpApiGet(FrappeTestCase):
	"""icorp_api_get function"""

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.get")
	def test_200_with_valid_json_returns_snake_case_dict(self, mock_get, mock_auth):
		"""200 with valid JSON returns snake_case dict"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"camelCaseKey": "value", "anotherKey": 123}
		mock_response.raise_for_status.return_value = None
		mock_get.return_value = mock_response

		result = icorp_api_get("endpoint")

		self.assertEqual(result["camel_case_key"], "value")
		self.assertEqual(result["another_key"], 123)

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.get")
	def test_200_with_invalid_json_raises(self, mock_get, mock_auth):
		"""200 with invalid JSON raises via frappe.throw"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.side_effect = ValueError("Invalid JSON")
		mock_response.text = "not json"
		mock_get.return_value = mock_response

		with self.assertRaises(frappe.ValidationError):
			icorp_api_get("endpoint")

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.get")
	def test_4xx_5xx_raises_with_error_message(self, mock_get, mock_auth):
		"""4xx/5xx raises via frappe.throw with extracted error message"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 404
		mock_response.json.return_value = {"message": "Not found"}
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
		mock_get.return_value = mock_response

		with self.assertRaises(frappe.ValidationError):
			icorp_api_get("endpoint")

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.get")
	def test_timeout_raises(self, mock_get, mock_auth):
		"""Timeout raises via frappe.throw"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})
		mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

		with self.assertRaises(frappe.ValidationError):
			icorp_api_get("endpoint")

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.get")
	def test_request_exception_raises(self, mock_get, mock_auth):
		"""RequestException raises via frappe.throw"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})
		mock_get.side_effect = requests.exceptions.RequestException("Connection error")

		with self.assertRaises(frappe.ValidationError):
			icorp_api_get("endpoint")


class TestIcorpApiPost(FrappeTestCase):
	"""icorp_api_post function"""

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.post")
	def test_200_returns_response_json(self, mock_post, mock_auth):
		"""200 returns response JSON"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"id": 1, "status": "created"}
		mock_post.return_value = mock_response

		result = icorp_api_post("endpoint", {"field_name": "value"})

		self.assertEqual(result["id"], 1)
		self.assertEqual(result["status"], "created")

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.post")
	def test_outgoing_data_converted_to_camel_case(self, mock_post, mock_auth):
		"""Outgoing data converted to camelCase"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {}
		mock_post.return_value = mock_response

		icorp_api_post("endpoint", {"snake_case_field": "value", "another_field": 123})

		call_args = mock_post.call_args
		sent_data = call_args.kwargs["json"]
		self.assertIn("snakeCaseField", sent_data)
		self.assertIn("anotherField", sent_data)
		self.assertNotIn("snake_case_field", sent_data)

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.post")
	def test_empty_fields_stripped(self, mock_post, mock_auth):
		"""Empty fields stripped before sending"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {}
		mock_post.return_value = mock_response

		icorp_api_post(
			"endpoint", {"field": "value", "empty_string": "", "empty_list": [], "none_field": None}
		)

		call_args = mock_post.call_args
		sent_data = call_args.kwargs["json"]
		self.assertIn("field", sent_data)
		self.assertNotIn("emptyString", sent_data)
		self.assertNotIn("emptyList", sent_data)
		self.assertNotIn("noneField", sent_data)

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.post")
	def test_invalid_json_response_logs_error_and_returns_error_dict(self, mock_post, mock_auth):
		"""Invalid JSON response logs error and returns error dict"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.side_effect = ValueError("Invalid JSON")
		mock_response.text = "not json"
		mock_post.return_value = mock_response

		result = icorp_api_post("endpoint", {"field": "value"})

		self.assertIn("error", result)
		self.assertEqual(result["error"], "Invalid JSON response")


class TestIcorpApiPut(FrappeTestCase):
	"""icorp_api_put function"""

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.put")
	def test_200_returns_response_json(self, mock_put, mock_auth):
		"""200 returns response JSON"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"id": 1, "updated": True}
		mock_response.raise_for_status.return_value = None
		mock_put.return_value = mock_response

		result = icorp_api_put("endpoint", {"field_name": "value"})

		self.assertEqual(result["id"], 1)
		self.assertEqual(result["updated"], True)

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.put")
	def test_http_error_raises(self, mock_put, mock_auth):
		"""HTTP error raises"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 400
		mock_response.json.return_value = {"message": "Bad request"}
		mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("400 Bad Request")
		mock_put.return_value = mock_response

		with self.assertRaises(frappe.ValidationError):
			icorp_api_put("endpoint", {"field": "value"})


class TestIcorpApiDelete(FrappeTestCase):
	"""icorp_api_delete function"""

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.delete")
	def test_200_returns_response_json(self, mock_delete, mock_auth):
		"""200 returns response JSON"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {"deleted": True}
		mock_response.raise_for_status.return_value = None
		mock_delete.return_value = mock_response

		result = icorp_api_delete("endpoint")

		self.assertEqual(result["deleted"], True)

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.delete")
	def test_optional_body_sent_as_json_when_provided(self, mock_delete, mock_auth):
		"""Optional body sent as JSON when provided"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {}
		mock_response.raise_for_status.return_value = None
		mock_delete.return_value = mock_response

		icorp_api_delete("endpoint", {"field": "value"})

		call_args = mock_delete.call_args
		self.assertIn("json", call_args.kwargs)
		self.assertIsNotNone(call_args.kwargs["json"])

	@patch("ivm.integrations.icorp.api.get_icorp_auth")
	@patch("ivm.integrations.icorp.api.requests.delete")
	def test_body_omitted_when_none(self, mock_delete, mock_auth):
		"""Body omitted when None"""
		mock_auth.return_value = ("https://api.icorp.com", {"Authorization": "Bearer token"})

		mock_response = MagicMock()
		mock_response.status_code = 200
		mock_response.json.return_value = {}
		mock_response.raise_for_status.return_value = None
		mock_delete.return_value = mock_response

		icorp_api_delete("endpoint", None)

		call_args = mock_delete.call_args
		self.assertNotIn("json", call_args.kwargs)


class TestIcorpGetCount(FrappeTestCase):
	"""icorp_get_count function"""

	@patch("ivm.integrations.icorp.api.icorp_api_get")
	def test_valid_response_returns_pagination_total_records(self, mock_get):
		"""Valid response returns pagination.total_records"""
		mock_get.return_value = {"pagination": {"total_records": 42}}

		result = icorp_get_count("endpoint")

		self.assertEqual(result, 42)

	@patch("ivm.integrations.icorp.api.icorp_api_get")
	def test_api_error_returns_0(self, mock_get):
		"""API error returns 0"""
		mock_get.side_effect = frappe.ValidationError("API error")

		result = icorp_get_count("endpoint")

		self.assertEqual(result, 0)

	@patch("ivm.integrations.icorp.api.icorp_api_get")
	def test_missing_pagination_returns_0(self, mock_get):
		"""Missing pagination key returns 0"""
		mock_get.return_value = {"data": []}

		result = icorp_get_count("endpoint")

		self.assertEqual(result, 0)


class TestExtractId(FrappeTestCase):
	"""extract_id function"""

	def test_response_with_data_id_returns_id(self):
		"""Response with data.id returns id"""
		response = {"data": {"id": 123}}
		result = extract_id(response, "entity")
		self.assertEqual(result, 123)

	def test_response_with_entity_type_id_returns_id(self):
		"""Response with data.{entity_type}Id returns id"""
		response = {"data": {"customerId": 456}}
		result = extract_id(response, "customer")
		self.assertEqual(result, 456)

	def test_response_with_entity_type_snake_case_id_returns_id(self):
		"""Response with data.{entity_type}_id returns id"""
		response = {"data": {"customer_id": 789}}
		result = extract_id(response, "customer")
		self.assertEqual(result, 789)

	def test_response_with_no_recognizable_key_returns_none(self):
		"""Response with no recognizable key returns None"""
		response = {"data": {"unknown_field": 999}}
		result = extract_id(response, "entity")
		self.assertIsNone(result)

	def test_warning_logged_when_no_id_found(self):
		"""Warning logged when no ID found"""
		response = {"data": {"field": "value"}}
		with patch("ivm.integrations.icorp.api.frappe.logger") as mock_logger:
			extract_id(response, "entity")
			mock_logger.return_value.warning.assert_called()

	def test_non_dict_response_returns_none(self):
		"""Non-dict response returns None"""
		result = extract_id("not a dict", "entity")
		self.assertIsNone(result)

	def test_none_response_returns_none(self):
		"""None response returns None"""
		result = extract_id(None, "entity")
		self.assertIsNone(result)

	def test_id_value_converted_to_int(self):
		"""ID value converted to int"""
		response = {"data": {"id": "999"}}
		result = extract_id(response, "entity")
		self.assertEqual(result, 999)
		self.assertIsInstance(result, int)

	def test_invalid_id_value_returns_none(self):
		"""Invalid ID value returns None"""
		response = {"data": {"id": "not_a_number"}}
		result = extract_id(response, "entity")
		self.assertIsNone(result)

	def test_unwraps_data_envelope(self):
		"""Unwraps data envelope if present"""
		response = {"data": {"id": 111}}
		result = extract_id(response, "entity")
		self.assertEqual(result, 111)

	def test_top_level_id_when_no_data_envelope(self):
		"""Uses top-level id when no data envelope"""
		response = {"id": 222}
		result = extract_id(response, "entity")
		self.assertEqual(result, 222)
