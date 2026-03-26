"""
SendGrid Inbound Parse webhook integration.

Receives inbound emails forwarded by SendGrid's Inbound Parse service and
creates Frappe Issues with ``issue_type='Support'``.  The ``after_insert``
hook on the Issue DocType automatically creates a linked Support Ticket.

Flow
----
1. SendGrid POSTs a multipart/form-data payload to ``/api/method/
   ivm.ivm_integrations.sendgrid.inbound_parse.receive``.
2. ``receive()`` validates the optional shared secret, applies a size guard,
   resolves the target Email Account from the ``to`` address, then
   immediately enqueues the heavy work and returns HTTP 200 so SendGrid
   never retries.
3. ``process_inbound_email()`` runs in a background worker, parses the raw
   RFC 2822 message via Frappe's ``InboundMail``, performs Message-ID
   deduplication, and inserts an Issue directly — bypassing
   ``mail.process()`` which only creates a Communication document.

Site-config keys
----------------
``sendgrid_inbound_secret`` (optional)
    Shared secret expected in the ``X-Webhook-Secret`` header or the
    ``webhook_secret`` form field.  If omitted, secret validation is
    skipped.  Comparison is always done with :func:`hmac.compare_digest`
    to prevent timing-attack leakage.
"""

from __future__ import annotations

import hmac as _hmac

import frappe
from frappe.email.receive import InboundMail
from frappe.utils.html_utils import sanitize_html

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hard ceiling on inbound payload size.  Emails larger than this are rejected
# immediately in the synchronous receive() handler so the worker queue is
# never polluted with unparseable multi-megabyte blobs.
MAX_RAW_EMAIL_BYTES: int = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Public webhook endpoint
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def receive() -> dict:
    """Accept an Inbound Parse POST from SendGrid.

    Always returns HTTP 200 (except for the missing-email-field 400 case)
    so SendGrid does not retry transient failures.  Heavy processing is
    offloaded to the background queue via :func:`frappe.enqueue`.
    """
    _validate_request()

    raw_email: str | None = frappe.request.form.get("email")
    if not raw_email:
        # "Send Raw" option is not enabled in SendGrid — nothing we can parse.
        frappe.response.http_status_code = 400
        return {
            "error": (
                "Missing 'email' field — enable 'Send Raw' in SendGrid "
                "Inbound Parse settings"
            )
        }

    # ------------------------------------------------------------------
    # CRIT-3: Size guard — reject oversized payloads before any further work
    # ------------------------------------------------------------------
    to_address: str = frappe.request.form.get("to") or ""
    if len(raw_email.encode("utf-8")) > MAX_RAW_EMAIL_BYTES:
        frappe.log_error(
            title="SendGrid Inbound Parse: oversized email rejected",
            message=(
                f"Email to '{to_address}' exceeded {MAX_RAW_EMAIL_BYTES} bytes "
                f"and was dropped."
            ),
        )
        return {"status": "rejected", "reason": "payload_too_large"}

    recipient_email: str = frappe.utils.extract_email_id(to_address)

    # Prefer an exact match on the recipient; fall back to the default
    # incoming account so misconfigured aliases still land somewhere.
    account_name: str | None = frappe.db.get_value(
        "Email Account",
        {"email_id": recipient_email, "enable_incoming": 1},
        "name",
    ) or frappe.db.get_value(
        "Email Account",
        {"enable_incoming": 1, "default_incoming": 1},
        "name",
    )

    if not account_name:
        frappe.log_error(
            title="SendGrid Inbound Parse: No matching Email Account",
            message=(
                f"Could not find an enabled incoming Email Account for recipient "
                f"'{recipient_email}'.  Create one or configure a default incoming "
                f"account."
            ),
        )
        # Return 200 so SendGrid does not keep retrying an unresolvable address.
        return {"status": "no_account"}

    frappe.enqueue(
        "ivm.ivm_integrations.sendgrid.inbound_parse.process_inbound_email",
        queue="short",
        raw_email=raw_email,
        account_name=account_name,
    )

    return {"status": "queued"}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


def process_inbound_email(raw_email: str, account_name: str) -> None:
    """Parse a raw RFC 2822 message and create a Support Issue.

    This function runs in a background worker.  Errors are logged with a full
    traceback so they can be investigated in the Frappe Error Log.

    The ``after_insert`` hook chain (``create_linked_ticket_on_insert``)
    fires synchronously on ``issue.insert()`` and handles its own
    ``frappe.db.commit()``.  We therefore do **not** commit here to avoid
    double-committing mid-hook.

    Args:
        raw_email:    Full RFC 2822 email message as a string (from SendGrid's
                      ``email`` form field when "Send Raw" is enabled).
        account_name: Name of the ``Email Account`` document to associate with
                      the inbound message.
    """
    try:
        email_account_doc = frappe.get_doc("Email Account", account_name)

        mail = InboundMail(
            content=raw_email,
            email_account=email_account_doc,
            uid=None,
            seen_status=None,
            append_to=None,
        )

        # ------------------------------------------------------------------
        # MAJ-4: Message-ID based idempotency guard
        # ------------------------------------------------------------------
        message_id: str | None = getattr(mail, "message_id", None) or None
        if message_id and frappe.db.get_value(
            "Issue",
            {"custom_email_message_id": message_id},
            "name",
        ):
            frappe.logger().info(
                f"SendGrid Inbound Parse: duplicate email "
                f"(message_id={message_id!r}), skipping."
            )
            return

        # ------------------------------------------------------------------
        # CRIT-2: Sanitise HTML; strip mail.content (contains raw headers)
        # ------------------------------------------------------------------
        raw_description: str = mail.get_content() or mail.text_content or ""
        description: str = sanitize_html(raw_description) if raw_description else ""

        # ------------------------------------------------------------------
        # MAJ-3: Validate sender address before storing as raised_by
        # ------------------------------------------------------------------
        from_email: str = mail.from_email or ""
        if from_email and not frappe.utils.is_valid_email(from_email):
            frappe.logger().warning(
                f"SendGrid Inbound Parse: ignoring invalid from_email "
                f"{from_email!r}; storing as empty string."
            )
            from_email = ""

        issue_data: dict = {
            "doctype": "Issue",
            "subject": mail.subject or "(No Subject)",
            "raised_by": from_email,
            "issue_type": "Support",
            "description": description,
            "via_customer_portal": 0,
        }

        # Only store message_id when the custom field exists on the Issue
        # DocType (avoids hard dependency on a DB migration being applied).
        if message_id and frappe.db.has_column("Issue", "custom_email_message_id"):
            issue_data["custom_email_message_id"] = message_id

        issue = frappe.get_doc(issue_data)
        issue.insert(ignore_permissions=True)
        # MAJ-2: Do NOT call frappe.db.commit() here — the after_insert hook
        # chain (create_linked_ticket_on_insert) commits itself.

        frappe.logger().info(
            f"SendGrid Inbound Parse: created Issue {issue.name!r} "
            f"from {from_email!r} (Email Account: {account_name!r})"
        )

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="SendGrid Inbound Parse: process_inbound_email failed",
            message=frappe.get_traceback(with_context=True),
        )
        raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_request() -> None:
    """Validate the optional shared-secret sent by SendGrid.

    The secret may be passed in the ``X-Webhook-Secret`` HTTP header *or* as
    the ``webhook_secret`` form field.  Validation is skipped entirely when
    ``sendgrid_inbound_secret`` is not present in ``site_config.json``.

    Comparison uses :func:`hmac.compare_digest` (constant-time) to prevent
    timing-attack leakage of the secret value.

    Raises:
        frappe.PermissionError: when a secret is configured but the provided
            value does not match, or when no value is provided at all.
    """
    expected: str | None = frappe.conf.get("sendgrid_inbound_secret")
    if not expected:
        return  # Secret checking is disabled for this site.

    provided: str | None = (
        frappe.request.headers.get("X-Webhook-Secret")
        or frappe.form_dict.get("webhook_secret")
    )
    if not provided or not _hmac.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise frappe.PermissionError("Invalid webhook secret")
