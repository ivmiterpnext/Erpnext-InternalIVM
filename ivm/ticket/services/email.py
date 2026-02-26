from __future__ import annotations

import re

import frappe
from frappe.utils import now_datetime


ITSUPPORT_INBOX = "itsupport@example.com"
IT_SUPPORT = "IT_SUPPORT"
EMAIL_SOURCE = "Email"
RECEIVED = "Received"
SENT = "Sent"
EMAIL = "Email"
TICKET = "Ticket"
PUBLIC = "Public"

TICKET_SUBJECT_PATTERN = re.compile(r"\[(TKT-\d{4}-\d{5})\]")


def handle_communication_after_insert(doc, method: str | None = None) -> None:
	if doc.doctype != "Communication":
		return

	if (doc.communication_type or "") != EMAIL:
		return

	ticket_name = _ensure_ticket_reference(doc)
	if not ticket_name:
		return

	_create_activity_from_communication(doc, ticket_name)


def _ensure_ticket_reference(doc) -> str | None:
	if doc.reference_doctype == TICKET and doc.reference_name:
		return doc.reference_name

	ticket_name = _extract_ticket_from_subject(doc.subject)
	if ticket_name:
		doc.db_set("reference_doctype", TICKET, update_modified=False)
		doc.db_set("reference_name", ticket_name, update_modified=False)
		return ticket_name

	if not _is_inbound_to_itsupport(doc):
		return None

	new_ticket = frappe.get_doc(
		{
			"doctype": TICKET,
			"subject": (doc.subject or "Email Request").strip(),
			"description": _clean_message(doc.content),
			"business_area": IT_SUPPORT,
			"source": EMAIL_SOURCE,
			"requester_email": _extract_sender_email(doc.sender),
		}
	)
	new_ticket.insert(ignore_permissions=True)

	doc.db_set("reference_doctype", TICKET, update_modified=False)
	doc.db_set("reference_name", new_ticket.name, update_modified=False)
	return new_ticket.name


def _extract_ticket_from_subject(subject: str | None) -> str | None:
	if not subject:
		return None

	match = TICKET_SUBJECT_PATTERN.search(subject)
	if not match:
		return None

	ticket_name = match.group(1)
	if frappe.db.exists(TICKET, ticket_name):
		return ticket_name

	return None


def _is_inbound_to_itsupport(doc) -> bool:
	if (doc.sent_or_received or "") != RECEIVED:
		return False

	recipients = ",".join(
		[
			doc.recipients or "",
			doc.cc or "",
			doc.bcc or "",
		]
	).lower()

	return ITSUPPORT_INBOX in recipients


def _create_activity_from_communication(doc, ticket_name: str) -> None:
	activity_type = "Email Inbound" if (doc.sent_or_received or "") == RECEIVED else "Email Outbound"

	activity = frappe.get_doc(
		{
			"doctype": "Ticket Activity",
			"ticket": ticket_name,
			"activity_type": activity_type,
			"visibility": PUBLIC,
			"message": _clean_message(doc.content) or (doc.subject or "Email update"),
			"communication": doc.name,
			"occurred_on": now_datetime(),
		}
	)
	activity.insert(ignore_permissions=True)

	frappe.db.set_value(
		TICKET,
		ticket_name,
		{
			"latest_activity_on": activity.occurred_on,
			"latest_activity_summary": activity.message[:280],
		},
		update_modified=False,
	)


def _extract_sender_email(sender: str | None) -> str:
	if not sender:
		return ""

	if "<" in sender and ">" in sender:
		parts = sender.split("<", maxsplit=1)
		return parts[1].replace(">", "").strip().lower()

	return sender.strip().lower()


def _clean_message(content: str | None) -> str:
	return (content or "").strip()
