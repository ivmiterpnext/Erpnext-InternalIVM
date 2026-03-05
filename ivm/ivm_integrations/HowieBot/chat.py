import requests

import frappe


@frappe.whitelist()
def send_message(message: str) -> dict:
	"""Forward a chat message to the HowieBot service and return its response."""
	if not message or not message.strip():
		frappe.throw("Message cannot be empty.")

	url = frappe.db.get_single_value("HowieBot Config", "url")
	if not url:
		frappe.throw(
			"HowieBot is not configured. Ask a System Manager to set the URL in HowieBot Config."
		)

	try:
		response = requests.post(
			url,
			json={"message": message.strip()},
			timeout=30,
		)
		response.raise_for_status()
		return response.json()
	except requests.exceptions.Timeout:
		frappe.log_error(
			title="HowieBot Timeout",
			message=f"Request to {url} timed out after 30s",
		)
		frappe.throw("HowieBot is taking too long to respond. Please try again later.")
	except requests.exceptions.HTTPError as e:
		frappe.log_error(
			title="HowieBot HTTP Error",
			message=f"Status {e.response.status_code}: {e.response.text[:500]}",
		)
		frappe.throw(f"HowieBot returned an error (HTTP {e.response.status_code}).")
	except requests.exceptions.RequestException as e:
		frappe.log_error(
			title="HowieBot Connection Error",
			message=str(e),
		)
		frappe.throw("Could not reach HowieBot. Please try again later.")
