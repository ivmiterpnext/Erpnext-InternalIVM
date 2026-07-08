"""
Sync HubSpot engagements (notes, calls, emails, tasks, meetings)
and their attachments to Frappe CRM activity records.
"""

import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

import frappe

from ivm.integrations.hubspot import api
from ivm.integrations.hubspot.constants import (
    ALL_ENGAGEMENT_TYPES,
    CALL_DIRECTION_MAP,
    CALL_STATUS_MAP,
    ENGAGEMENT_PROPERTIES,
    ENGAGEMENT_TYPE_CALLS,
    ENGAGEMENT_TYPE_EMAILS,
    ENGAGEMENT_TYPE_MEETINGS,
    ENGAGEMENT_TYPE_NOTES,
    ENGAGEMENT_TYPE_TASKS,
    HUBSPOT_DEAL_ID_FIELD,
    HUBSPOT_ENGAGEMENT_ID_FIELD,
    TASK_PRIORITY_MAP,
    TASK_STATUS_MAP,
)

_LOG = "hubspot"

# HubSpot captures calendar responses (accept/decline) as email engagements.
# We convert these to FCRM Notes instead of Communications.
_CALENDAR_PREFIXES = ("Accepted:", "Declined:", "Tentative:", "Canceled:", "New Time Proposed:")

_CALENDAR_ACTION_MAP = {
    "Accepted":  "accepted",
    "Declined":  "declined",
    "Tentative": "tentatively accepted",
    "Canceled":  "canceled",
    "New Time Proposed": "proposed a new time for",
}

# Pre-compiled patterns for stripping quoted replies from email threads.
_RE_OUTLOOK_QUOTE = re.compile(
    r'<div[^>]*border-top\s*:\s*solid[^>]*>.*',
    re.IGNORECASE | re.DOTALL,
)
_RE_GMAIL_QUOTE = re.compile(
    r'<blockquote[^>]*class=["\'][^"\']*gmail_quote[^"\']*["\'][^>]*>.*',
    re.IGNORECASE | re.DOTALL,
)
_RE_PLAIN_QUOTE = re.compile(
    r'\r?\n\r?\n(?:From|On .+ wrote):\s',
    re.IGNORECASE,
)


def _normalize_email_list(value: str) -> str:
    if not value:
        return ""
    return ", ".join(addr.strip() for addr in value.replace(";", ",").split(",") if addr.strip())


def sync_deal_activities(hubspot_deal_id: int | str, crm_deal_name: str) -> None:
    """Fetch and sync all engagement types for a HubSpot deal."""

    for engagement_type in ALL_ENGAGEMENT_TYPES:
        try:
            _sync_engagement_type(engagement_type, hubspot_deal_id, crm_deal_name)
        except Exception:
            frappe.log_error(
                title=(
                    f"HubSpot: failed to sync {engagement_type} "
                    f"for deal {hubspot_deal_id}"
                ),
                message=frappe.get_traceback(with_context=True),
            )


def handle_engagement_webhook(
    engagement_type: str,
    engagement_id: int | str,
    hubspot_user_id: int | str | None = None,
) -> None:
    """Handle a single engagement webhook event.

    Looks up associated deal(s) and syncs the engagement to each one.
    """
    from ivm.integrations.hubspot.sync_utils import set_acting_user

    set_acting_user(hubspot_user_id)

    engagement_id_str = str(engagement_id)

    try:
        deal_ids = api.get_engagement_deal_ids(engagement_type, engagement_id_str)
    except api.HubSpotRateLimitExhausted:
        frappe.logger(_LOG).warning(
            f"HubSpot: rate limit exhausted fetching deal associations for {engagement_type} {engagement_id_str} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.activity_handler.handle_engagement_webhook",
            queue="long",
            engagement_type=engagement_type,
            engagement_id=engagement_id,
            hubspot_user_id=hubspot_user_id,
        )
        return
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch deal associations for {engagement_type} {engagement_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    if not deal_ids:
        frappe.logger(_LOG).info(
            f"No deal associated with {engagement_type} {engagement_id_str} — skipping"
        )
        return

    properties = ENGAGEMENT_PROPERTIES.get(engagement_type, [])
    try:
        data = api.get_engagement(engagement_type, engagement_id_str, properties)
    except api.HubSpotRateLimitExhausted:
        frappe.logger(_LOG).warning(
            f"HubSpot: rate limit exhausted fetching {engagement_type} {engagement_id_str} — re-enqueueing"
        )
        frappe.enqueue(
            "ivm.integrations.hubspot.activity_handler.handle_engagement_webhook",
            queue="long",
            engagement_type=engagement_type,
            engagement_id=engagement_id,
            hubspot_user_id=hubspot_user_id,
        )
        return
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch {engagement_type} {engagement_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    props = data.get("properties", {})
    # Fallback timestamp when hs_timestamp is missing.
    if "createdAt" not in props and data.get("createdAt"):
        props["_createdAt"] = data["createdAt"]
    handler = _TYPE_HANDLERS.get(engagement_type)
    if handler is None:
        frappe.logger(_LOG).warning(
            f"No handler for engagement type '{engagement_type}'"
        )
        return

    for deal_id in deal_ids:
        crm_deal_name = frappe.db.get_value(
            "CRM Deal", {HUBSPOT_DEAL_ID_FIELD: str(deal_id)}, "name",
        )
        if not crm_deal_name:
            frappe.logger(_LOG).warning(
                f"No CRM Deal for HubSpot deal {deal_id} — "
                f"skipping {engagement_type} {engagement_id_str}"
            )
            continue

        try:
            handler(engagement_id_str, props, crm_deal_name)
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to sync {engagement_type} {engagement_id_str} "
                      f"to CRM Deal {crm_deal_name}",
                message=frappe.get_traceback(with_context=True),
            )


def _sync_engagement_type(
    engagement_type: str,
    hubspot_deal_id: int | str,
    crm_deal_name: str,
) -> None:
    """Fetch engagement IDs of a given type and sync each one."""

    engagement_ids = api.get_deal_engagement_ids(
        hubspot_deal_id, engagement_type,
    )
    if not engagement_ids:
        return

    properties = ENGAGEMENT_PROPERTIES.get(engagement_type, [])
    handler = _TYPE_HANDLERS[engagement_type]

    for eid in engagement_ids:
        try:
            data = api.get_engagement(engagement_type, eid, properties)
            props = data.get("properties", {})
            handler(str(eid), props, crm_deal_name)
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to sync {engagement_type} {eid}",
                message=frappe.get_traceback(with_context=True),
            )


@contextmanager
def _as_owner(hubspot_owner_id: str | None):
    """Context manager that temporarily switches the Frappe session user for
    correct ``owner`` attribution.  Yields the resolved email (or None).
    """
    if not hubspot_owner_id:
        yield None
        return

    email = api.get_owner_email(hubspot_owner_id)
    if email and frappe.db.exists("User", email):
        prev = frappe.session.user
        frappe.set_user(email)
        try:
            yield email
        finally:
            frappe.set_user(prev)
    else:
        yield None


def _sync_attachments(
    hs_attachment_ids: str | None,
    crm_deal_name: str,
) -> None:
    """Download HubSpot file attachments and attach them to the CRM Deal.

    ``hs_attachment_ids`` is a semicolon-separated string of HubSpot file IDs.
    Deduplication uses the ``hs_{file_id}_`` filename prefix.
    """
    if not hs_attachment_ids:
        return

    file_ids = [fid.strip() for fid in hs_attachment_ids.split(";") if fid.strip()]

    for file_id in file_ids:
        already_exists = frappe.db.get_value(
            "File",
            filters=[
                ["attached_to_doctype", "=", "CRM Deal"],
                ["attached_to_name", "=", crm_deal_name],
                ["file_name", "like", f"hs_{file_id}_%"],
            ],
            fieldname="name",
        )
        if already_exists:
            continue

        result = api.download_file(file_id)
        if result is None:
            continue

        filename, content = result
        safe_name = f"hs_{file_id}_{filename}"

        try:
            file_doc = frappe.new_doc("File")
            file_doc.file_name = safe_name
            file_doc.attached_to_doctype = "CRM Deal"
            file_doc.attached_to_name = crm_deal_name
            file_doc.content = content
            file_doc.is_private = 1
            file_doc.save(ignore_permissions=True)
            frappe.logger(_LOG).info(
                f"Attached file '{safe_name}' to CRM Deal {crm_deal_name}"
            )
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to attach file {file_id}",
                message=frappe.get_traceback(with_context=True),
            )


def _sync_note(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create or update an FCRM Note from a HubSpot note engagement.

    Attachment-only notes (no body) are skipped; files still sync to the deal.
    """
    body = props.get("hs_note_body") or ""
    attachment_ids = props.get("hs_attachment_ids") or ""

    existing_name = _get_existing("FCRM Note", engagement_id)
    if existing_name:
        if body:
            doc = frappe.get_doc("FCRM Note", existing_name)
            doc.content = body
            doc.save(ignore_permissions=True)
            frappe.logger(_LOG).info(
                f"Updated FCRM Note {existing_name} from HubSpot note {engagement_id}"
            )
        _sync_attachments(attachment_ids, crm_deal_name)
        return

    # Attachment-only: sync files but skip empty FCRM Note.
    if not body:
        if attachment_ids:
            _sync_attachments(attachment_ids, crm_deal_name)
            frappe.logger(_LOG).info(
                f"Synced attachments from HubSpot note {engagement_id} "
                f"to CRM Deal {crm_deal_name} (no body — skipped FCRM Note)"
            )
        return

    with _as_owner(props.get("hubspot_owner_id")):
        doc = frappe.new_doc("FCRM Note")
        doc.title = "HubSpot Note"
        doc.content = body
        doc.reference_doctype = "CRM Deal"
        doc.reference_docname = crm_deal_name
        doc.set(HUBSPOT_ENGAGEMENT_ID_FIELD, engagement_id)
        doc.insert(ignore_permissions=True)

        _sync_attachments(attachment_ids, crm_deal_name)

        frappe.logger(_LOG).info(
            f"Synced HubSpot note {engagement_id} → FCRM Note {doc.name}"
        )


def _sync_call(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create or update a CRM Call Log from a HubSpot call engagement."""

    existing_name = _get_existing("CRM Call Log", engagement_id)
    if existing_name:
        status_raw = (props.get("hs_call_status") or "").upper()
        status = CALL_STATUS_MAP.get(status_raw)
        recording_url = props.get("hs_call_recording_url")
        if status or recording_url:
            doc = frappe.get_doc("CRM Call Log", existing_name)
            if status:
                doc.status = status
            if recording_url:
                doc.recording_url = recording_url
            doc.save(ignore_permissions=True)
            frappe.logger(_LOG).info(
                f"Updated CRM Call Log {existing_name} from HubSpot call {engagement_id}"
            )
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        return

    direction = (props.get("hs_call_direction") or "").upper()
    call_type = CALL_DIRECTION_MAP.get(direction, "Outgoing")

    status_raw = (props.get("hs_call_status") or "").upper()
    status = CALL_STATUS_MAP.get(status_raw, "Completed")

    from_number = props.get("hs_call_from_number") or ""
    to_number = props.get("hs_call_to_number") or ""

    duration_ms = props.get("hs_call_duration")
    duration_secs = 0
    if duration_ms:
        try:
            duration_secs = int(duration_ms) // 1000
        except (ValueError, TypeError):
            pass

    with _as_owner(props.get("hubspot_owner_id")) as owner_email:
        doc = frappe.new_doc("CRM Call Log")
        doc.id = f"HS-CALL-{engagement_id}"
        doc.type = call_type
        doc.status = status
        doc.duration = duration_secs
        doc.start_time = _parse_timestamp(props.get("hs_timestamp"))
        doc.recording_url = props.get("hs_call_recording_url") or ""
        doc.reference_doctype = "CRM Deal"
        doc.reference_docname = crm_deal_name
        doc.telephony_medium = "Manual"
        doc.set(HUBSPOT_ENGAGEMENT_ID_FIELD, engagement_id)

        doc.set("from", from_number or "Unknown")
        doc.to = to_number or "Unknown"

        if owner_email:
            if call_type == "Outgoing":
                doc.caller = owner_email
            else:
                doc.receiver = owner_email

        doc.insert(ignore_permissions=True)

        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)

        frappe.logger(_LOG).info(
            f"Synced HubSpot call {engagement_id} → CRM Call Log {doc.name}"
        )


def _create_calendar_note(
    engagement_id: str, props: dict[str, Any], crm_deal_name: str,
) -> None:
    """Create an FCRM Note for a calendar accept/decline/tentative/cancel response."""
    if _get_existing("FCRM Note", engagement_id):
        return

    raw_subject = (props.get("hs_email_subject") or "").strip()

    action = "responded to"
    meeting_title = raw_subject
    for prefix, label in _CALENDAR_ACTION_MAP.items():
        if raw_subject.startswith(f"{prefix}:"):
            action = label
            meeting_title = raw_subject[len(prefix) + 1:].strip()
            break

    contact_email = (
        props.get("hs_email_from_email")
        or props.get("hs_email_sender_email")
        or ""
    )
    contact_display = _resolve_contact_name(contact_email) if contact_email else "The contact"

    if action == "proposed a new time for":
        tag = "New Time Proposed"
    else:
        tag = f"Meeting {action.replace('tentatively ', '').capitalize()}"
    title = f"[{tag}] {meeting_title}" if meeting_title else f"[{tag}]"

    content = f"{contact_display} {action} the meeting invite: **{meeting_title}**."

    with _as_owner(props.get("hubspot_owner_id")):
        doc = frappe.new_doc("FCRM Note")
        doc.title = _truncate(title, 140)
        doc.content = content
        doc.reference_doctype = "CRM Deal"
        doc.reference_docname = crm_deal_name
        doc.set(HUBSPOT_ENGAGEMENT_ID_FIELD, engagement_id)
        doc.insert(ignore_permissions=True)
        frappe.logger(_LOG).info(
            f"Created calendar note for HubSpot email {engagement_id} → FCRM Note {doc.name}"
        )


def _sync_email(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create a Communication from a HubSpot email engagement."""

    # Calendar responses are routed to FCRM Notes instead.
    raw_subject = (props.get("hs_email_subject") or "").strip()
    if raw_subject.startswith(_CALENDAR_PREFIXES):
        _create_calendar_note(engagement_id, props, crm_deal_name)
        return

    # Deduplicate via message_id; still sync attachments in case they were missed.
    message_id = f"<hubspot-email-{engagement_id}>"
    if frappe.db.exists("Communication", {"message_id": message_id}):
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        return

    send_status = (props.get("hs_email_status") or "").upper()
    is_logged = send_status == "MANUALLY_CHANGED"
    subject = "Logged Email" if is_logged else (props.get("hs_email_subject") or "No Subject")

    direction = (props.get("hs_email_direction") or "").upper()
    is_inbound = direction == "INCOMING_EMAIL"
    sent_or_received = "Received" if is_inbound else "Sent"

    # Inbound: from_email = contact, sender_email = CRM owner (not the real sender).
    if is_inbound:
        sender = props.get("hs_email_from_email") or props.get("hs_email_sender_email") or ""
        recipients = _normalize_email_list(props.get("hs_email_to_email") or "")
    else:
        sender = props.get("hs_email_sender_email") or ""
        recipients = _normalize_email_list(props.get("hs_email_to_email") or "")

    cc = _normalize_email_list(props.get("hs_email_cc_email") or "")
    bcc = _normalize_email_list(props.get("hs_email_bcc_email") or "")

    html_body = props.get("hs_email_html") or ""
    text_body = props.get("hs_email_text") or ""
    raw_content = html_body or text_body
    content = _strip_quoted_reply(raw_content, bool(html_body))

    comm_date = (
        _parse_timestamp(props.get("hs_timestamp"))
        or _parse_timestamp(props.get("_createdAt"))
    )

    with _as_owner(props.get("hubspot_owner_id")):
        doc = frappe.new_doc("Communication")
        doc.subject = subject
        doc.content = content
        doc.communication_type = "Communication"
        doc.communication_medium = "Email"
        doc.sent_or_received = sent_or_received
        doc.sender = sender
        doc.recipients = recipients
        doc.cc = cc
        doc.bcc = bcc
        doc.communication_date = comm_date
        doc.reference_doctype = "CRM Deal"
        doc.reference_name = crm_deal_name
        doc.message_id = message_id
        doc.has_attachment = 1 if props.get("hs_attachment_ids") else 0
        doc.insert(ignore_permissions=True)

        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)

        frappe.logger(_LOG).info(
            f"Synced HubSpot email {engagement_id} → Communication {doc.name}"
        )


def _sync_task(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create or update a CRM Task from a HubSpot task engagement."""

    title = props.get("hs_task_subject") or "HubSpot Task"
    description = props.get("hs_task_body") or ""

    status_raw = (props.get("hs_task_status") or "").upper()
    status = TASK_STATUS_MAP.get(status_raw, "Todo")

    priority_raw = (props.get("hs_task_priority") or "").upper()
    priority = TASK_PRIORITY_MAP.get(priority_raw, "Medium")

    existing_name = _get_existing("CRM Task", engagement_id)
    if existing_name:
        doc = frappe.get_doc("CRM Task", existing_name)
        doc.title = title
        doc.description = description
        doc.status = status
        doc.priority = priority
        doc.save(ignore_permissions=True)
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        frappe.logger(_LOG).info(
            f"Updated CRM Task {existing_name} from HubSpot task {engagement_id}"
        )
        return

    with _as_owner(props.get("hubspot_owner_id")) as owner_email:
        doc = frappe.new_doc("CRM Task")
        doc.title = title
        doc.description = description
        doc.status = status
        doc.priority = priority
        doc.reference_doctype = "CRM Deal"
        doc.reference_docname = crm_deal_name
        doc.set(HUBSPOT_ENGAGEMENT_ID_FIELD, engagement_id)

        if owner_email:
            doc.assigned_to = owner_email

        doc.insert(ignore_permissions=True)

        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)

        frappe.logger(_LOG).info(
            f"Synced HubSpot task {engagement_id} → CRM Task {doc.name}"
        )


def _sync_meeting(
    engagement_id: str, props: dict[str, Any], crm_deal_name: str,
) -> None:
    """Create or update an FCRM Note from a HubSpot meeting engagement."""

    title = props.get("hs_meeting_title") or "Meeting"
    body = props.get("hs_meeting_body") or ""
    start = _parse_timestamp(props.get("hs_meeting_start_time"))
    end = _parse_timestamp(props.get("hs_meeting_end_time"))

    # Build rich content with meeting metadata
    content_parts: list[str] = []
    if start:
        time_line = f"**Start:** {start}"
        if end:
            time_line += f"  |  **End:** {end}"
        content_parts.append(time_line)
    if body:
        content_parts.append(body)
    content = "<br>".join(content_parts) if content_parts else ""

    existing_name = _get_existing("FCRM Note", engagement_id)
    if existing_name:
        doc = frappe.get_doc("FCRM Note", existing_name)
        doc.title = f"[Meeting] {title}"
        doc.content = content
        doc.save(ignore_permissions=True)
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        frappe.logger(_LOG).info(
            f"Updated FCRM Note {existing_name} from HubSpot meeting {engagement_id}"
        )
        return

    with _as_owner(props.get("hubspot_owner_id")):
        doc = frappe.new_doc("FCRM Note")
        doc.title = f"[Meeting] {title}"
        doc.content = content
        doc.reference_doctype = "CRM Deal"
        doc.reference_docname = crm_deal_name
        doc.set(HUBSPOT_ENGAGEMENT_ID_FIELD, engagement_id)
        doc.insert(ignore_permissions=True)

        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)

        frappe.logger(_LOG).info(
            f"Synced HubSpot meeting {engagement_id} → FCRM Note {doc.name}"
        )


_TYPE_HANDLERS: dict[str, Any] = {
    ENGAGEMENT_TYPE_NOTES: _sync_note,
    ENGAGEMENT_TYPE_CALLS: _sync_call,
    ENGAGEMENT_TYPE_EMAILS: _sync_email,
    ENGAGEMENT_TYPE_TASKS: _sync_task,
    ENGAGEMENT_TYPE_MEETINGS: _sync_meeting,
}


def _get_existing(doctype: str, engagement_id: str) -> str | None:
    """Return the Frappe document name for this HubSpot engagement, or None."""
    return frappe.db.get_value(doctype, {HUBSPOT_ENGAGEMENT_ID_FIELD: engagement_id}, "name")


def _parse_timestamp(value: str | None) -> str | None:
    """Convert a HubSpot timestamp (epoch-ms or ISO-8601 UTC) to a Frappe
    system-timezone datetime string.
    """
    if not value:
        return None

    utc_dt: datetime | None = None

    try:
        epoch_ms = int(value)
        utc_dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        # Try ISO-8601 string (e.g. "2026-06-03T16:45:20.000Z")
        if isinstance(value, str) and "T" in value:
            clean = value.replace("Z", "+00:00")
            try:
                utc_dt = datetime.fromisoformat(clean)
                if utc_dt.tzinfo is None:
                    utc_dt = utc_dt.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                return None

    if utc_dt is None:
        return None

    local_dt = frappe.utils.data.convert_utc_to_system_timezone(utc_dt)
    return local_dt.strftime("%Y-%m-%d %H:%M:%S")


def _resolve_contact_name(email: str) -> str:
    """Return a contact's full name for the given email, falling back to the email itself."""
    if not email:
        return email

    result = frappe.db.get_value(
        "Contact",
        {"email_id": email.lower()},
        ["first_name", "last_name"],
        as_dict=True,
    )
    if not result:
        return email

    first = (result.get("first_name") or "").strip()
    last = (result.get("last_name") or "").strip()
    full = " ".join(filter(None, [first, last]))
    return full or email


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to *max_len* characters, adding ellipsis if needed."""
    clean = re.sub(r"<[^>]+>", "", text).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1] + "…"


def _strip_quoted_reply(content: str, is_html: bool) -> str:
    """Strip the quoted previous email from a threaded reply, keeping only the new text."""
    if not content:
        return content

    if is_html:
        for pat in (_RE_OUTLOOK_QUOTE, _RE_GMAIL_QUOTE):
            match = pat.search(content)
            if match:
                content = content[: match.start()].strip()
                break
        return content

    match = _RE_PLAIN_QUOTE.search(content)
    if match:
        content = content[: match.start()].strip()

    # Strip ">" quote markers.
    lines = content.splitlines()
    trimmed = []
    for line in lines:
        if line.startswith(">"):
            break
        trimmed.append(line)
    content = "\n".join(trimmed).strip()

    return content
