from typing import Any

import frappe
import requests

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_TOKEN_HEADER = "Authorization"


def on_wiki_document_update(doc: Any, method: str | None = None) -> None:
	if not _content_changed(doc):
		return

	# Skip if content is empty
	if not (doc.content or "").strip():
		return

	payload = _build_payload(doc)

	try:
		frappe.enqueue(
			"ivm.ivm_integrations.wiki.content_webhook.send_wiki_content_webhook",
			queue="short",
			payload=payload,
		)
	except Exception:
		frappe.log_error(
			title="Wiki content webhook enqueue failed",
			message=frappe.get_traceback(with_context=True),
		)


def send_wiki_content_webhook(payload: dict[str, Any]) -> None:
	webhook_url = "http://127.0.0.1"
	if not webhook_url:
		return

	headers = {"Content-Type": "application/json"}
	token = frappe.conf.get("wiki_content_webhook_token")
	if token:
		token_header = frappe.conf.get("wiki_content_webhook_token_header") or DEFAULT_TOKEN_HEADER
		headers[str(token_header)] = str(token)

	timeout_seconds = cint_or_default(frappe.conf.get("wiki_content_webhook_timeout"), DEFAULT_TIMEOUT_SECONDS)

	try:
		response = requests.post(
			str(webhook_url),
			json=payload,
			headers=headers,
			timeout=timeout_seconds,
		)
		response.raise_for_status()
	except Exception:
		frappe.log_error(
			title="Wiki content webhook send failed",
			message=frappe.get_traceback(with_context=True),
		)


def _content_changed(doc: Any) -> bool:
	if getattr(doc, "doctype", "") != "Wiki Document":
		return False

	has_value_changed = getattr(doc, "has_value_changed", None)
	if callable(has_value_changed):
		try:
			return bool(has_value_changed("content"))
		except Exception:
			pass

	if getattr(doc, "is_new", lambda: False)():
		return True

	before_save = getattr(doc, "get_doc_before_save", lambda: None)()
	if not before_save:
		return True

	return (before_save.content or "") != (doc.content or "")


def _build_payload(doc: Any) -> dict[str, Any]:
	return {
		"content": doc.content or "",
	}


def cint_or_default(value: Any, default: int) -> int:
	try:
		return int(value)
	except (TypeError, ValueError):
		return default
