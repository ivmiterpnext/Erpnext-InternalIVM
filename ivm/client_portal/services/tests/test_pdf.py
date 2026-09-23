"""Integration tests for ivm.client_portal.services.pdf"""

from unittest.mock import patch

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.client_portal.services.pdf import download_quote_pdf

_DOWNLOAD_PDF_TARGET = "frappe.utils.print_format.download_pdf"


def _make_contact(first_name, user=None):
	contact = frappe.get_doc({"doctype": "Contact", "first_name": first_name, "user": user})
	contact.insert(ignore_permissions=True)
	return contact


def _make_quote(signers=None):
	top_contact = _make_contact(f"Top {frappe.generate_hash(length=6)}")
	doc = frappe.get_doc(
		{
			"doctype": "Service Quote",
			"contact": top_contact.name,
			"sales_representative": "Administrator",
			"customer": "_Test Customer",
			"signers": signers or [],
		}
	)
	doc.insert(ignore_permissions=True)
	with patch("ivm.client_portal.event_handlers.service_quote.on_submit"):
		doc.submit()
	return doc


class TestDownloadQuotePdf(ERPNextTestSuite):
	def test_denies_non_signer(self):
		quote = _make_quote()
		with self.assertRaises(frappe.PermissionError):
			download_quote_pdf(quote.name)

	def test_allows_signer_and_delegates_to_core(self):
		signer_contact = _make_contact("Signer PDF", user="Administrator")
		quote = _make_quote(signers=[{"contact": signer_contact.name}])

		with patch(_DOWNLOAD_PDF_TARGET, return_value=b"fake-pdf-bytes") as mock_download:
			result = download_quote_pdf(quote.name)

		mock_download.assert_called_once()
		call_kwargs = mock_download.call_args.kwargs
		self.assertEqual(call_kwargs["doctype"], "Service Quote")
		self.assertEqual(call_kwargs["name"], quote.name)
		self.assertEqual(result, b"fake-pdf-bytes")

	def test_logs_view_pdf_activity(self):
		signer_contact = _make_contact("Signer PDF Log", user="Administrator")
		quote = _make_quote(signers=[{"contact": signer_contact.name}])

		with patch(_DOWNLOAD_PDF_TARGET, return_value=b"x"):
			download_quote_pdf(quote.name)

		log_exists = frappe.db.exists(
			"Service Quote Activity Log",
			{"service_quote": quote.name, "event_type": "View PDF"},
		)
		self.assertTrue(log_exists)
