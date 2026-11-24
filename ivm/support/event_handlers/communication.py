import re

import frappe

from ivm.support.utils import fetch_customer_name_and_contact

SUPPORT_ISSUE_TYPES = ["IT", "Support", "Receivable", "Reconfiguration", "Vending Management"]

# RFC 5322 header folding: a line break followed by horizontal whitespace is a
# continuation, not a real separator — collapse to a single space.
_FOLDING_WHITESPACE_PATTERN = re.compile(r"[\r\n]+[ \t]+")
# Defensive: collapse any leftover bare CR/LF not part of a proper fold too,
# so a raw newline can never reach email.utils.getaddresses().
_STRAY_NEWLINE_PATTERN = re.compile(r"[\r\n]+")


def on_update(doc, method):
	if doc.reference_doctype != "Issue":
		return

	try:
		attachments = doc.get_attachments()
		reference_name = frappe.get_all(
			"Communication", filters={"reference_name": doc.reference_name}, fields=["reference_name"]
		)
		# getting record matching to email received
		email = None
		if doc.email_account:
			email = frappe.db.get_value("Email Account", {"name": doc.email_account}, "name")

		if email:
			email_Account = frappe.get_doc("Email Account", email)
			# getting issue type from email account doctype
			issue_type = email_Account.imap_folder[0].custom_issue_type
			issue_name = frappe.get_doc("Issue", doc.reference_name)
			if issue_type in SUPPORT_ISSUE_TYPES:
				customer = fetch_customer_name_and_contact(doc.sender)
				if customer:
					issue_name.customer = customer.get("customer_name")
					issue_name.contact_name = customer.get("contact_name")
			issue_name.issue_type = issue_type
			if len(reference_name) <= 1:
				issue_name.description = doc.content
			issue_name.save()
			if attachments:
				file_urls = [url["file_url"] for url in attachments]
				for file_url in file_urls:
					already_attached = frappe.db.exists(
						"File",
						{
							"file_url": file_url,
							"attached_to_doctype": "Issue",
							"attached_to_name": doc.reference_name,
						},
					)
					if already_attached:
						continue
					file = frappe.get_doc(
						{
							"doctype": "File",
							"is_private": 1,
							"file_url": file_url,
							"attached_to_doctype": "Issue",
							"attached_to_name": doc.reference_name,
						}
					)
					file.save()
			frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ivm.support.event_handlers.communication.on_update error")


def sanitize_email_header_fields(doc, method):
	"""before_validate hook: normalize recipients/cc/bcc before
	Communication.validate() calls set_timeline_links() -> get_contacts()
	-> email.utils.getaddresses().

	Fixes two independent malformed-header classes seen in incoming mail:
	1. RFC 5322 header folding left un-collapsed (continuation lines stored
	   with the literal \\n/\\t still in the field), e.g.
	   '"Danielle\\n Lanteigne" <d_lanteigne@ivminc.com>'. Python 3.13+'s
	   stricter email.utils.getaddresses mis-splits these, producing a
	   corrupted standalone token ('Danielle') that then fails Contact
	   auto-creation's email validation.
	2. Stray mismatched quotes not wrapping a full "Name" <addr> pair
	   (pre-existing fix, logic unchanged, renamed only).

	Order matters: unfold first, so _strip_stray_quotes operates on
	single-line, already-sane input.
	"""
	for field in ("recipients", "cc", "bcc"):
		value = doc.get(field)
		if value:
			value = _unfold_header_whitespace(value)
			value = _strip_stray_quotes(value)
			doc.set(field, value)


def _unfold_header_whitespace(email_str):
	unfolded = _FOLDING_WHITESPACE_PATTERN.sub(" ", email_str)
	return _STRAY_NEWLINE_PATTERN.sub(" ", unfolded)


def _strip_stray_quotes(email_str):
	placeholders = []

	def protect(match):
		placeholders.append(match.group(0))
		return f"\x00{len(placeholders) - 1}\x00"

	protected = re.sub(r'(?:(?<=^)|(?<=,))(\s*"[^"]*"\s*<[^>]+>)', protect, email_str)
	cleaned = protected.replace('"', "")

	for i, original in enumerate(placeholders):
		cleaned = cleaned.replace(f"\x00{i}\x00", original)

	return cleaned
