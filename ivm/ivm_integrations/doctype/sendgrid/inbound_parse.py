import frappe

from frappe.email.receive import InboundMail, SentEmailInInboxError
@frappe.whitelist(allow_guest=True)  # SendGrid can't use Frappe API tokens
def receive():
    _validate_request()  # optional shared-secret check
    raw_email = frappe.request.form.get("email")  # full RFC 2822 message from SendGrid
    if not raw_email:
        frappe.response.http_status_code = 400
        return {"error": "Missing 'email' field"}
    # Match by recipient address to the correct Email Account
    to_address = frappe.request.form.get("to", "")
    recipient_email = frappe.utils.extract_email_id(to_address)
    account_name = frappe.db.get_value(
        "Email Account",
        {"email_id": recipient_email, "enable_incoming": 1},
        "name",
    ) or frappe.db.get_value(
        "Email Account",
        {"enable_incoming": 1, "default_incoming": 1},
        "name",
    )
    if not account_name:
        frappe.log_error("SendGrid Inbound Parse: No matching Email Account found")
        return {"status": "no_account"}  # Return 200 so SendGrid doesn't retry
    email_account_doc = frappe.get_doc("Email Account", account_name)
    try:
        mail = InboundMail(
            content=raw_email,
            email_account=email_account_doc,
            uid=None,
            seen_status=0,
        )
        communication = mail.process()
        frappe.db.commit()
        return {"status": "ok", "communication": communication.name if communication else None}
    except SentEmailInInboxError:
        frappe.db.rollback()
        return {"status": "skipped"}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="SendGrid Inbound Parse Error")
        return {"status": "error"}  # Still return 200 to avoid infinite retries
def _validate_request():
    """Lightweight shared-secret validation."""
    expected = frappe.conf.get("sendgrid_inbound_secret")
    if expected:
        provided = frappe.request.headers.get("X-Webhook-Secret") or frappe.form_dict.get("webhook_secret")
        if provided != expected:
            raise frappe.PermissionError("Invalid webhook secret")
