"""Override for frappe.core.doctype.communication.communication.get_emails.

Frappe core's get_emails() calls email.utils.getaddresses() with zero
preprocessing. Python 3.13+ rewrote getaddresses to a strict RFC 5322 parser;
a single malformed/corrupted address mixed in with otherwise-valid ones can
produce a corrupted result for that one token without rejecting the rest of
the list — unlike the "whole list discarded" failure mode that
frappe.utils.validate_email_address already guards against via an
isolation-reparse fallback (commit 4dd546ae0d, "Getaddresses used in
isolation for input if it bails out") — but that fix exists only on
Frappe's unreleased `develop` branch, is not backported to version-16
(confirmed 2026-11-24), and only patches validate_email_address, not
get_contacts/get_emails.

This is defense-in-depth alongside
ivm.support.event_handlers.communication.sanitize_email_header_fields, which
fixes the specific root cause observed so far (un-collapsed RFC 5322 header
folding). This override additionally guards get_contacts()'s auto-contact-
creation path against any other malformed-address shape: if any address
extracted from a field looks invalid, each comma-separated piece is
re-parsed in isolation (frappe.utils.split_emails is quote-aware) so one bad
entry can never corrupt or suppress its valid neighbours.

Monkeypatched (not override_whitelisted_methods) since get_emails is a plain
internal function, not a whitelisted endpoint — reassigning the module
attribute from ivm/__init__.py redirects get_contacts()'s bare-name call to
it (same technique as ivm/overrides/queue_overload_fix.py).

Remove this patch when Frappe core backports the isolation-reparse fix to
get_contacts/get_emails for the version-16 branch we run.
"""

from email.utils import getaddresses

from frappe.utils import EMAIL_MATCH_PATTERN, split_emails


def _is_valid_address(addr):
	return bool(addr) and bool(EMAIL_MATCH_PATTERN.fullmatch(addr))


def get_emails_patched(email_strings):
	email_addrs = []
	for email_string in email_strings:
		if not email_string:
			continue

		result = getaddresses([email_string])
		non_empty = [addr for _, addr in result if addr]
		if non_empty and not all(_is_valid_address(addr) for addr in non_empty):
			result = []
			for piece in split_emails(email_string):
				result.extend(getaddresses([piece]))

		email_addrs.extend(addr for _, addr in result if _is_valid_address(addr))

	return email_addrs


def apply() -> None:
	"""Replace get_emails in the communication module."""
	import frappe.core.doctype.communication.communication as communication

	communication.get_emails = get_emails_patched
