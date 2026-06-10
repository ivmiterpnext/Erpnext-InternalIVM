"""
Sync HubSpot engagements (notes, calls, emails, tasks, meetings)
and their attachments to Frappe CRM activity records.
"""

import re
from datetime import datetime, timezone
from typing import Any

import frappe

from ivm.ivm_integrations.hubspot import hubspot_client
from ivm.ivm_integrations.hubspot.constants import (
    ALL_ENGAGEMENT_TYPES,
    CALL_DIRECTION_MAP,
    CALL_STATUS_MAP,
    ENGAGEMENT_PROPERTIES,
    ENGAGEMENT_TYPE_CALLS,
    ENGAGEMENT_TYPE_EMAILS,
    ENGAGEMENT_TYPE_MEETINGS,
    ENGAGEMENT_TYPE_NOTES,
    ENGAGEMENT_TYPE_TASKS,
    HUBSPOT_ENGAGEMENT_ID_FIELD,
    TASK_PRIORITY_MAP,
    TASK_STATUS_MAP,
)

_LOG = "hubspot"

# Calendar response subject prefixes — HubSpot captures meeting accept/decline
# notifications from connected inboxes as email engagements.  We convert these
# to lightweight FCRM Notes instead of Communications.
_CALENDAR_PREFIXES = ("Accepted:", "Declined:", "Tentative:", "Canceled:")

# Maps the subject prefix to a human-readable action label.
_CALENDAR_ACTION_MAP = {
    "Accepted":  "accepted",
    "Declined":  "declined",
    "Tentative": "tentatively accepted",
    "Canceled":  "canceled",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


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
    """Handle a single engagement event from a generic webhook subscription.

    Looks up the associated deal(s) via reverse association and syncs the
    engagement to each deal.  Called from ``webhook.py`` via ``frappe.enqueue``.
    """
    from ivm.ivm_integrations.hubspot.sync_utils import set_acting_user

    set_acting_user(hubspot_user_id)

    engagement_id_str = str(engagement_id)

    # Find deal(s) associated with this engagement
    try:
        deal_ids = hubspot_client.get_engagement_deal_ids(engagement_type, engagement_id_str)
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

    # Fetch the engagement data once
    properties = ENGAGEMENT_PROPERTIES.get(engagement_type, [])
    try:
        data = hubspot_client.get_engagement(engagement_type, engagement_id_str, properties)
    except Exception:
        frappe.log_error(
            title=f"HubSpot: failed to fetch {engagement_type} {engagement_id_str}",
            message=frappe.get_traceback(with_context=True),
        )
        return

    props = data.get("properties", {})
    # Inject top-level createdAt as a fallback timestamp — the properties
    # dict may not always contain a usable hs_timestamp.
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
            "CRM Deal", {"custom_hubspot_deal_id": str(deal_id)}, "name",
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


# ---------------------------------------------------------------------------
# Per-type dispatcher
# ---------------------------------------------------------------------------

# Maps engagement type → handler function.
_TYPE_HANDLERS: dict[str, Any] = {}  # populated after function definitions


def _sync_engagement_type(
    engagement_type: str,
    hubspot_deal_id: int | str,
    crm_deal_name: str,
) -> None:
    """Fetch engagement IDs of a given type and sync each one."""

    engagement_ids = hubspot_client.get_deal_engagement_ids(
        hubspot_deal_id, engagement_type,
    )
    if not engagement_ids:
        return

    properties = ENGAGEMENT_PROPERTIES.get(engagement_type, [])
    handler = _TYPE_HANDLERS.get(engagement_type)
    if handler is None:
        frappe.logger(_LOG).warning(
            f"No handler for engagement type '{engagement_type}'"
        )
        return

    for eid in engagement_ids:
        try:
            data = hubspot_client.get_engagement(engagement_type, eid, properties)
            props = data.get("properties", {})
            handler(str(eid), props, crm_deal_name)
        except Exception:
            frappe.log_error(
                title=f"HubSpot: failed to sync {engagement_type} {eid}",
                message=frappe.get_traceback(with_context=True),
            )


# ---------------------------------------------------------------------------
# User attribution helper
# ---------------------------------------------------------------------------


def _set_owner_for_insert(
    hubspot_owner_id: str | None,
) -> tuple[str | None, str | None]:
    """Temporarily switch the Frappe session user for correct ``owner`` attribution.

    Returns ``(previous_user, resolved_email)`` so the caller can restore
    the session and use the resolved email for additional attribution
    (e.g. ``caller``, ``assigned_to``) without a redundant API call.
    """
    if not hubspot_owner_id:
        return None, None

    email = hubspot_client.get_owner_email(hubspot_owner_id)
    if email and frappe.db.exists("User", email):
        prev = frappe.session.user
        frappe.set_user(email)
        return prev, email
    return None, None


def _restore_user(prev_user: str | None) -> None:
    """Restore the Frappe session user after an attributed insert."""
    if prev_user:
        frappe.set_user(prev_user)


# ---------------------------------------------------------------------------
# Attachment sync
# ---------------------------------------------------------------------------


def _sync_attachments(
    hs_attachment_ids: str | None,
    crm_deal_name: str,
) -> None:
    """Download HubSpot file attachments and attach them to the CRM Deal.

    Files are attached directly to the CRM Deal so they appear in the
    deal's Attachments tab.  ``hs_attachment_ids`` is a semicolon-separated
    string of HubSpot file IDs.

    Deduplication uses the ``hs_{file_id}_`` filename prefix — a single
    indexed LIKE lookup that avoids any HubSpot API call if the file is
    already present.
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

        result = hubspot_client.download_file(file_id)
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


# ---------------------------------------------------------------------------
# Notes → FCRM Note
# ---------------------------------------------------------------------------


def _sync_note(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create an FCRM Note from a HubSpot note engagement.

    Attachment-only notes (no body text) are skipped — their files are
    still synced to the CRM Deal's Attachments tab, but no empty FCRM
    Note is created.
    """
    if _engagement_exists("FCRM Note", engagement_id):
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        return

    body = props.get("hs_note_body") or ""
    attachment_ids = props.get("hs_attachment_ids") or ""
    owner_id = props.get("hubspot_owner_id")

    # Attachment-only note: sync files to the deal but don't create
    # an empty FCRM Note — the files show in the Attachments tab.
    if not body:
        if attachment_ids:
            _sync_attachments(attachment_ids, crm_deal_name)
            frappe.logger(_LOG).info(
                f"Synced attachments from HubSpot note {engagement_id} "
                f"to CRM Deal {crm_deal_name} (no note body — skipped FCRM Note)"
            )
        return

    prev_user, _ = _set_owner_for_insert(owner_id)
    try:
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
    finally:
        _restore_user(prev_user)


# ---------------------------------------------------------------------------
# Calls → CRM Call Log
# ---------------------------------------------------------------------------


def _sync_call(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create a CRM Call Log from a HubSpot call engagement."""

    if _engagement_exists("CRM Call Log", engagement_id):
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
            duration_secs = int(int(duration_ms) / 1000)
        except (ValueError, TypeError):
            pass

    owner_id = props.get("hubspot_owner_id")

    prev_user, owner_email = _set_owner_for_insert(owner_id)
    try:
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

        # Set from/to numbers — required fields
        doc.set("from", from_number or "Unknown")
        doc.to = to_number or "Unknown"

        # Attribute caller/receiver if the owner resolved to a Frappe user
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
    finally:
        _restore_user(prev_user)


# ---------------------------------------------------------------------------
# Calendar responses → FCRM Note
# ---------------------------------------------------------------------------


def _create_calendar_note(
    engagement_id: str, props: dict[str, Any], crm_deal_name: str,
) -> None:
    """Create an FCRM Note for a calendar accept/decline/tentative/cancel response.

    HubSpot captures these as INCOMING_EMAIL engagements with no body content.
    Rather than showing them as empty Communications, we create a short FCRM
    Note that conveys the response clearly.
    """
    if _engagement_exists("FCRM Note", engagement_id):
        return

    raw_subject = (props.get("hs_email_subject") or "").strip()

    # Extract action and meeting title from subject, e.g.
    # "Accepted: IVM Smart Vault Project Check In" → action="accepted", title="IVM Smart Vault..."
    action = "responded to"
    meeting_title = raw_subject
    for prefix, label in _CALENDAR_ACTION_MAP.items():
        if raw_subject.startswith(f"{prefix}:"):
            action = label
            meeting_title = raw_subject[len(prefix) + 1:].strip()
            break

    # Resolve the contact's full name from their email address.
    # Fall back to the email address itself if no matching Contact exists.
    contact_email = (
        props.get("hs_email_from_email")
        or props.get("hs_email_sender_email")
        or ""
    )
    contact_display = _resolve_contact_name(contact_email) if contact_email else "The contact"

    # Title: "[Meeting Accepted] IVM Smart Vault Project Check In"
    action_label = action.replace("tentatively ", "").capitalize()
    title = f"[Meeting {action_label}] {meeting_title}" if meeting_title else f"[Meeting {action_label}]"

    content = f"{contact_display} {action} the meeting invite: **{meeting_title}**."

    owner_id = props.get("hubspot_owner_id")
    prev_user, _ = _set_owner_for_insert(owner_id)
    try:
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
    finally:
        _restore_user(prev_user)


# Emails → Communication
# ---------------------------------------------------------------------------


def _sync_email(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create a Communication from a HubSpot email engagement."""

    # Calendar accept/decline/tentative/cancel responses are captured by HubSpot
    # as email engagements but have no body content. Route them to FCRM Notes.
    raw_subject = (props.get("hs_email_subject") or "").strip()
    if raw_subject.startswith(_CALENDAR_PREFIXES):
        _create_calendar_note(engagement_id, props, crm_deal_name)
        return

    # Deduplicate via message_id on Communication, but still sync attachments
    # in case they were missed on the first pass (e.g. download was broken).
    message_id = f"<hubspot-email-{engagement_id}>"
    if frappe.db.exists("Communication", {"message_id": message_id}):
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        return

    # A manually-logged email (BCC-captured or CRM-logged) has no real send
    # status. Inbound replies arrive with INBOX/READ which are not send statuses
    # — those still have a real subject and should not be overwritten.
    send_status = (props.get("hs_email_status") or "").upper()
    is_logged = send_status == "MANUALLY_CHANGED"
    subject = "Logged Email" if is_logged else (props.get("hs_email_subject") or "No Subject")

    # HubSpot direction values for outgoing: EMAIL, FORWARDED_EMAIL
    # Inbound reply from contact: INCOMING_EMAIL
    direction = (props.get("hs_email_direction") or "").upper()
    is_inbound = direction == "INCOMING_EMAIL"
    sent_or_received = "Received" if is_inbound else "Sent"

    # For inbound emails, hs_email_from_email holds the contact's actual address.
    # hs_email_sender_email is the CRM owner (the person who receives the reply
    # in their connected inbox) — not the real sender.
    if is_inbound:
        sender = props.get("hs_email_from_email") or props.get("hs_email_sender_email") or ""
        recipients = props.get("hs_email_to_email") or ""
    else:
        sender = props.get("hs_email_sender_email") or ""
        recipients = props.get("hs_email_to_email") or ""

    cc = props.get("hs_email_cc_email") or ""
    bcc = props.get("hs_email_bcc_email") or ""

    html_body = props.get("hs_email_html") or ""
    text_body = props.get("hs_email_text") or ""
    raw_content = html_body or text_body
    # Strip the quoted previous email from threaded replies so only the new
    # message body is stored.
    content = _strip_quoted_reply(raw_content, bool(html_body))

    comm_date = (
        _parse_timestamp(props.get("hs_timestamp"))
        or _parse_timestamp(props.get("_createdAt"))
    )

    owner_id = props.get("hubspot_owner_id")
    prev_user, _ = _set_owner_for_insert(owner_id)
    try:
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
    finally:
        _restore_user(prev_user)


# ---------------------------------------------------------------------------
# Tasks → CRM Task
# ---------------------------------------------------------------------------


def _sync_task(engagement_id: str, props: dict[str, Any], crm_deal_name: str) -> None:
    """Create a CRM Task from a HubSpot task engagement."""

    if _engagement_exists("CRM Task", engagement_id):
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        return

    title = props.get("hs_task_subject") or "HubSpot Task"
    description = props.get("hs_task_body") or ""

    status_raw = (props.get("hs_task_status") or "").upper()
    status = TASK_STATUS_MAP.get(status_raw, "Todo")

    priority_raw = (props.get("hs_task_priority") or "").upper()
    priority = TASK_PRIORITY_MAP.get(priority_raw, "Medium")

    owner_id = props.get("hubspot_owner_id")

    prev_user, owner_email = _set_owner_for_insert(owner_id)
    try:
        doc = frappe.new_doc("CRM Task")
        doc.title = title
        doc.description = description
        doc.status = status
        doc.priority = priority
        doc.reference_doctype = "CRM Deal"
        doc.reference_docname = crm_deal_name
        doc.set(HUBSPOT_ENGAGEMENT_ID_FIELD, engagement_id)

        # Assign to the HubSpot owner if they resolved to a Frappe user
        if owner_email:
            doc.assigned_to = owner_email

        doc.insert(ignore_permissions=True)

        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)

        frappe.logger(_LOG).info(
            f"Synced HubSpot task {engagement_id} → CRM Task {doc.name}"
        )
    finally:
        _restore_user(prev_user)


# ---------------------------------------------------------------------------
# Meetings → FCRM Note (with [Meeting] prefix)
# ---------------------------------------------------------------------------


def _sync_meeting(
    engagement_id: str, props: dict[str, Any], crm_deal_name: str,
) -> None:
    """Create an FCRM Note from a HubSpot meeting engagement."""

    if _engagement_exists("FCRM Note", engagement_id):
        _sync_attachments(props.get("hs_attachment_ids"), crm_deal_name)
        return

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

    owner_id = props.get("hubspot_owner_id")

    prev_user, _ = _set_owner_for_insert(owner_id)
    try:
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
    finally:
        _restore_user(prev_user)


# ---------------------------------------------------------------------------
# Wire up the handler dispatch table
# ---------------------------------------------------------------------------

_TYPE_HANDLERS.update({
    ENGAGEMENT_TYPE_NOTES: _sync_note,
    ENGAGEMENT_TYPE_CALLS: _sync_call,
    ENGAGEMENT_TYPE_EMAILS: _sync_email,
    ENGAGEMENT_TYPE_TASKS: _sync_task,
    ENGAGEMENT_TYPE_MEETINGS: _sync_meeting,
})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _engagement_exists(doctype: str, engagement_id: str) -> bool:
    """Check whether a Frappe record already exists for this HubSpot engagement."""
    return bool(
        frappe.db.exists(doctype, {HUBSPOT_ENGAGEMENT_ID_FIELD: engagement_id})
    )


def _parse_timestamp(value: str | None) -> str | None:
    """Convert a HubSpot timestamp to a Frappe datetime string in the system timezone.

    HubSpot sends epoch-millisecond integers or ISO-8601 strings (UTC).
    Frappe stores naive datetimes that are implicitly in the system
    timezone, so we must convert from UTC to local time.
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
    """Return a contact's full name given their email address.

    Looks up the Contact by primary email.  Falls back to the email address
    itself if no match is found, so the note always has something meaningful.
    """
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
    # Strip HTML tags for a cleaner title
    clean = re.sub(r"<[^>]+>", "", text).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1] + "…"


def _strip_quoted_reply(content: str, is_html: bool) -> str:
    """Strip the quoted previous email from a threaded reply.

    Email clients include the original message below a separator.  We keep
    only the new text so the Communication record shows just the latest reply.

    HTML emails: Outlook wraps the quote in a div with a top border rule
    (``border:none;border-top:solid``).  Gmail uses a ``<blockquote>`` with
    ``class="gmail_quote"``.

    Plain-text emails: Outlook/standard clients precede the quote with a line
    starting with ``From:`` after a blank line, or with ``> `` quote markers.
    """
    if not content:
        return content

    if is_html:
        # Outlook quoted block: <div style="...border:none;border-top:solid...">
        # The style contains both "border:none" and "border-top:solid" as separate
        # declarations, so we match on "border-top:solid" which is the reliable marker.
        outlook_pat = re.compile(
            r'<div[^>]*border-top\s*:\s*solid[^>]*>.*',
            re.IGNORECASE | re.DOTALL,
        )
        # Gmail quoted block: <blockquote class="gmail_quote"...>
        gmail_pat = re.compile(
            r'<blockquote[^>]*class=["\'][^"\']*gmail_quote[^"\']*["\'][^>]*>.*',
            re.IGNORECASE | re.DOTALL,
        )
        for pat in (outlook_pat, gmail_pat):
            match = pat.search(content)
            if match:
                content = content[: match.start()].strip()
                break
        return content

    # Plain text: strip from the standard "From:" attribution line onwards.
    # Matches a blank line followed by "From: Name <email>" (Outlook style).
    plain_pat = re.compile(r'\r?\n\r?\n(?:From|On .+ wrote):\s', re.IGNORECASE)
    match = plain_pat.search(content)
    if match:
        content = content[: match.start()].strip()

    # Also strip lines starting with ">" (RFC 3676 quote markers)
    lines = content.splitlines()
    trimmed = []
    for line in lines:
        if line.startswith(">"):
            break
        trimmed.append(line)
    content = "\n".join(trimmed).strip()

    return content
