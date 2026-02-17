import frappe
from frappe import _


def verify_hubspot_request():
	"""Verify that the incoming request has a valid shared secret.

	HubSpot Workflow webhook actions should be configured to send
	an ``X-HubSpot-Secret: <secret>`` header where ``<secret>``
	matches the value stored in **HubSpot Settings > Webhook Secret**.

	Raises:
		frappe.AuthenticationError: If the integration is disabled or the
			secret does not match.
	"""
	settings = frappe.get_cached_doc("HubSpot Settings")

	if not settings.enabled:
		frappe.throw(
			_("HubSpot integration is disabled."),
			frappe.AuthenticationError,
		)

	token = frappe.request.headers.get("X-HubSpot-Secret", "")
	if not token:
		frappe.throw(
			_("Missing X-HubSpot-Secret header."),
			frappe.AuthenticationError,
		)

	expected = settings.get_password("webhook_secret")

	if token != expected:
		frappe.throw(
			_("Invalid webhook secret."),
			frappe.AuthenticationError,
		)


def _get_stage_mapping() -> dict[str, str]:
	"""Return a dict mapping HubSpot stage identifiers to CRM Deal Status names.

	The mapping is read from the **HubSpot Settings** child table and cached
	in memory for the duration of the request.
	"""
	settings = frappe.get_cached_doc("HubSpot Settings")
	return {
		row.hubspot_stage: row.crm_deal_status
		for row in settings.stage_mapping
	}


def _resolve_status(hubspot_stage: str) -> str:
	"""Translate a HubSpot deal stage identifier to a CRM Deal Status name.

	Raises:
		frappe.ValidationError: If no mapping exists for the given stage.
	"""
	mapping = _get_stage_mapping()
	status = mapping.get(hubspot_stage)
	if not status:
		frappe.throw(
			_("No CRM Deal Status mapping found for HubSpot stage: {0}").format(
				hubspot_stage
			),
			frappe.ValidationError,
		)
	return status


def _parse_deal_data(data: dict) -> dict:
	"""Extract and normalise deal fields from the HubSpot webhook payload.

	Expected payload keys (sent by a HubSpot Workflow webhook action):

	.. code-block:: json

		{
			"objectId": 12345,
			"dealname": "Acme Corp Deal",
			"dealstage": "qualifiedtobuy",
			"pipeline": "default",
			"amount": "50000",
			"closedate": "2026-03-15",
			"hubspot_owner_id": "67890",
			"createdate": "2026-02-17T10:00:00Z",
			"hs_lastmodifieddate": "2026-02-17T10:00:00Z"
		}

	Returns:
		A dict suitable for passing to ``frappe.get_doc`` / ``doc.update``.
	"""
	amount = data.get("amount")
	if amount is not None:
		try:
			amount = float(amount)
		except (ValueError, TypeError):
			amount = 0

	return {
		"hubspot_deal_id": str(data.get("objectId", "")),
		"deal_name": data.get("dealname", ""),
		"status": _resolve_status(data.get("dealstage", "")),
		"deal_value": amount or 0,
		"expected_closure_date": data.get("closedate") or None,
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def deal_creation():
	"""Webhook endpoint for HubSpot: new deal created.

	URL: ``POST /api/method/ivm.ivm_integrations.hubspot.hubspot_webhook.deal_creation``

	The HubSpot Workflow should include deal properties in the JSON body
	and an ``Authorization: Bearer <secret>`` header.

	Idempotent: if a CRM Deal with the same ``hubspot_deal_id`` already
	exists, the request is acknowledged without creating a duplicate.
	"""
	try:
		verify_hubspot_request()

		data = frappe.request.get_json(force=True)
		if not data:
			frappe.throw(_("Empty request body."), frappe.ValidationError)

		deal_fields = _parse_deal_data(data)
		hubspot_deal_id = deal_fields.get("hubspot_deal_id")

		if not hubspot_deal_id:
			frappe.throw(
				_("objectId is required in the webhook payload."),
				frappe.ValidationError,
			)

		# Idempotency: skip if already imported
		existing = frappe.db.get_value(
			"CRM Deal", {"hubspot_deal_id": hubspot_deal_id}, "name"
		)
		if existing:
			return {"status": "skipped", "deal": existing, "reason": "already exists"}

		deal = frappe.new_doc("CRM Deal")
		deal.update(
			{
				"hubspot_deal_id": hubspot_deal_id,
				"status": deal_fields.get("status"),
				"deal_value": deal_fields.get("deal_value"),
				"expected_closure_date": deal_fields.get("expected_closure_date"),
			}
		)
		deal.insert(ignore_permissions=True)

		return {"status": "created", "deal": deal.name}

	except frappe.AuthenticationError:
		raise
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			_("HubSpot deal_creation webhook error"),
		)
		raise


@frappe.whitelist(allow_guest=True, methods=["POST"])
def deal_stage_update():
	"""Webhook endpoint for HubSpot: deal stage changed.

	URL: ``POST /api/method/ivm.ivm_integrations.hubspot.hubspot_webhook.deal_stage_update``

	The HubSpot Workflow should include at least ``objectId`` and
	``dealstage`` in the JSON body plus an ``Authorization: Bearer <secret>``
	header.

	If no CRM Deal exists for the given ``objectId``, a new deal is created
	(graceful handling for out-of-order webhooks).
	"""
	try:
		verify_hubspot_request()

		data = frappe.request.get_json(force=True)
		if not data:
			frappe.throw(_("Empty request body."), frappe.ValidationError)

		deal_fields = _parse_deal_data(data)
		hubspot_deal_id = deal_fields.get("hubspot_deal_id")

		if not hubspot_deal_id:
			frappe.throw(
				_("objectId is required in the webhook payload."),
				frappe.ValidationError,
			)

		new_status = deal_fields.get("status")

		existing = frappe.db.get_value(
			"CRM Deal", {"hubspot_deal_id": hubspot_deal_id}, "name"
		)

		if existing:
			deal = frappe.get_doc("CRM Deal", existing)
			deal.status = new_status

			# If the new status is "Lost" and a lost_reason was provided,
			# set it to avoid validation errors.
			lost_reason = data.get("lost_reason")
			if (
				frappe.db.get_value("CRM Deal Status", new_status, "type") == "Lost"
				and not deal.lost_reason
			):
				deal.lost_reason = lost_reason or "Other"
				if deal.lost_reason == "Other" and not deal.lost_notes:
					deal.lost_notes = data.get("lost_notes", "Closed via HubSpot")

			deal.save(ignore_permissions=True)

			return {"status": "updated", "deal": deal.name}

		# Deal does not exist yet — create it (handles out-of-order webhooks)
		deal = frappe.new_doc("CRM Deal")
		deal.update(
			{
				"hubspot_deal_id": hubspot_deal_id,
				"status": new_status,
				"deal_value": deal_fields.get("deal_value"),
				"expected_closure_date": deal_fields.get("expected_closure_date"),
			}
		)
		deal.insert(ignore_permissions=True)

		return {"status": "created", "deal": deal.name}

	except frappe.AuthenticationError:
		raise
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			_("HubSpot deal_stage_update webhook error"),
		)
		raise
