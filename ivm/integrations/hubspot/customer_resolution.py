"""
Explicit CRM Organization → Customer resolution for HubSpot-synced data.

A CRM Organization (one per HubSpot company) can point at one Customer via
``custom_customer``. CRM Deals carry their own ``custom_customer`` that wins
over the organization's link when both are set. Won-deal provisioning uses
``resolve_deal_customer``. When nothing resolves, the Won deal's Projects are
created with a blank Customer, and the deployer sets it on the Project.
Setting the Customer on a Project applies it to the deal, sibling Projects,
and organization (see ``apply_deal_customer``).
"""

from __future__ import annotations

from typing import Any

import frappe

_LOG = "hubspot"

DEAL_LEVEL_ONLY = "Deal-level only"


def run_guarded(title: str, fn: Any, *args: Any, **kwargs: Any) -> bool:
	"""Run ``fn`` inside a savepoint. On any error, roll back its partial writes, log to the
	Error Log under ``title`` and return False. Never re-raises, so a Customer-resolution
	failure cannot block the user's save. Returns True when ``fn`` completed.
	"""
	savepoint = "ivm_customer_resolution"
	frappe.db.savepoint(savepoint)
	try:
		fn(*args, **kwargs)
		return True
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		frappe.log_error(title=title, message=frappe.get_traceback(with_context=True))
		return False


def _enabled_customer(name: str | None) -> str | None:
	"""Return ``name`` if it is an existing, enabled Customer, else None."""
	if not name:
		return None
	disabled = frappe.db.get_value("Customer", name, "disabled")
	if disabled is None or disabled:
		return None
	return name


def resolve_deal_customer(deal: Any) -> str | None:
	"""Return the Customer to use for a CRM Deal, or None.

	The deal's own ``custom_customer`` wins over its organization's link when
	both point at enabled Customers that differ (a warning is logged).
	"""
	deal_candidate = _enabled_customer(deal.get("custom_customer"))

	org_candidate = None
	if deal.get("organization"):
		org = frappe.db.get_value(
			"CRM Organization",
			deal.organization,
			["custom_customer", "custom_resolution_mode"],
			as_dict=True,
		)
		# A "Deal-level only" organization maps to several Customers; never trust its link.
		if org and org.custom_resolution_mode != DEAL_LEVEL_ONLY:
			org_candidate = _enabled_customer(org.custom_customer)

	if deal_candidate and org_candidate and deal_candidate != org_candidate:
		frappe.logger(_LOG).warning(
			f"CRM Deal {deal.name}: deal Customer '{deal_candidate}' differs from "
			f"organization '{deal.get('organization')}' Customer '{org_candidate}' — using deal's value"
		)
		return deal_candidate

	return deal_candidate or org_candidate


def _same_value(a: Any, b: Any) -> bool:
	"""Blank-insensitive comparison: None, "" and 0-as-blank are treated the same for Links."""
	return (a if a not in (None, "") else None) == (b if b not in (None, "") else None)


def set_value_tracked(doctype: str, name: str, values: dict) -> None:
	"""Write ``values`` with ``frappe.db.set_value`` (no controller hooks) and record the change.

	If anything actually changes and ``doctype`` has ``track_changes`` on, one Version
	row is inserted in the same format Frappe writes for a normal save:
	``{"added": [], "changed": [[field, old, new], ...], "removed": [], ...}``.
	An unchanged write does nothing. Used for automatic writes made by the Customer
	resolution code, so they show on the record's Version/activity history.
	"""
	current = frappe.db.get_value(doctype, name, list(values), as_dict=True) or {}
	changed = [
		[field, current.get(field), new]
		for field, new in values.items()
		if not _same_value(current.get(field), new)
	]
	if not changed:
		return

	frappe.db.set_value(doctype, name, values)

	if not frappe.get_meta(doctype).track_changes:
		return

	frappe.get_doc(
		{
			"doctype": "Version",
			"ref_doctype": doctype,
			"docname": name,
			"data": frappe.as_json(
				{
					"added": [],
					"changed": changed,
					"removed": [],
					"row_changed": [],
					"data_import": None,
					"updater_reference": None,
				}
			),
		}
	).insert(ignore_permissions=True)


def validate_org(doc: Any, method: str | None = None) -> None:
	"""CRM Organization validate hook: record how ``custom_customer`` was set, and refuse an
	organization-wide Customer on a "Deal-level only" organization.

	The automatic path (_learn_org_customer, source "Deal") never sets a link on a Deal-level
	organization, so only a manual set is blocked here.
	"""
	if not (doc.has_value_changed("custom_customer") and doc.custom_customer):
		return
	source = doc.flags.get("customer_assignment_source") or "Manual"
	if doc.custom_resolution_mode == DEAL_LEVEL_ONLY and source != "Deal":
		frappe.throw(
			"This organization is Deal-level only: its deals resolve to different Customers, so set "
			"the Customer on each deal instead. Clear 'Customer Resolution Mode' first if you really "
			"want an organization-wide Customer."
		)
	doc.custom_customer_assignment_source = source


def on_org_customer_set(doc: Any, method: str | None = None) -> None:
	"""CRM Organization on_update hook: propagate a blank → set ``custom_customer``.

	Only fills deals/projects that have no Customer yet; never overwrites.
	"""
	if not (doc.has_value_changed("custom_customer") and doc.custom_customer):
		return
	before = doc.get_doc_before_save()
	if before and before.get("custom_customer"):
		return

	deals = frappe.get_all(
		"CRM Deal",
		filters={
			"organization": doc.name,
			"status": "Won",
			"custom_customer": ["in", ["", None]],
		},
		pluck="name",
	)

	for deal_name in deals:
		# One deal failing must not stop the others on this organization.
		run_guarded(
			f"Organization Customer propagation failed for CRM Deal {deal_name}",
			_backfill_won_deal_customer,
			deal_name,
			doc.custom_customer,
		)


def _backfill_won_deal_customer(deal_name: str, customer_name: str) -> None:
	"""Fill one Won deal's blank Client from its organization, and its Projects."""
	from ivm.deployments.services.provision_client_from_deal import (
		_link_contact_to_customer,
		get_primary_contact,
	)

	set_value_tracked("CRM Deal", deal_name, {"custom_customer": customer_name})

	deal = frappe.get_doc("CRM Deal", deal_name)
	primary_contact = get_primary_contact(deal)
	if primary_contact:
		_link_contact_to_customer(primary_contact, customer_name)

	_fill_deal_projects(deal_name, customer_name)


def load_hubspot_companies(doc: Any, method: str | None = None) -> None:
	"""Customer onload hook: attach the CRM Organizations linked to this Customer."""
	rows = frappe.get_all(
		"CRM Organization",
		filters={"custom_customer": doc.name},
		fields=["name", "organization_name", "custom_hubspot_company_id"],
	)
	for row in rows:
		row["deal_count"] = frappe.db.count("CRM Deal", {"organization": row.name})
	doc.set_onload("hubspot_companies", rows)


def apply_deal_customer(crm_deal_name: str, customer_name: str) -> None:
	"""Apply a confirmed Customer to a CRM Deal and everything hanging off it.

	Shared by the Won-transition path (deal.on_update), the manual-Client-on-Won
	path (on_deal_customer_set) and a Project's Customer when its deal has no
	Client (on_project_customer_set). Never saves the CRM Deal, so it cannot
	recurse into the CRM Deal hooks.

	Only fills a blank deal Client: a Client already set on the deal is never
	overwritten (the call is logged and does nothing). Otherwise it sets the
	Client, links the primary contact, fills blank Projects of the deal, and
	learns the Customer onto the organization.
	"""
	from ivm.deployments.services.provision_client_from_deal import (
		_link_contact_to_customer,
		get_primary_contact,
	)

	current = frappe.db.get_value("CRM Deal", crm_deal_name, "custom_customer")
	if current and current != customer_name:
		frappe.logger(_LOG).warning(
			f"CRM Deal {crm_deal_name} already has Client '{current}'; not overwriting with '{customer_name}'"
		)
		return

	set_value_tracked("CRM Deal", crm_deal_name, {"custom_customer": customer_name})

	deal = frappe.get_doc("CRM Deal", crm_deal_name)

	primary_contact = get_primary_contact(deal)
	if primary_contact:
		_link_contact_to_customer(primary_contact, customer_name)

	_fill_deal_projects(crm_deal_name, customer_name)

	if deal.organization:
		run_guarded(
			f"Organization learning failed for CRM Deal {crm_deal_name}",
			_learn_org_customer,
			deal.organization,
			customer_name,
			crm_deal_name,
		)


def _fill_deal_projects(crm_deal_name: str, customer_name: str) -> None:
	"""Fill the Customer and iCorp client on the deal's Projects that are missing them.

	- Projects with a blank Customer get customer_name.
	- Projects whose Customer is blank or already customer_name, and whose
	  icorp_client_id is blank, get the Customer's single "own" iCorp client when
	  there is exactly one (plus partner fields), mirroring create_projects_from_deal.
	Projects already on a different Customer are never touched, and an existing
	iCorp client is never overwritten. Writes go through set_value_tracked, so Project validate
	does not run here.
	"""
	from ivm.deployments.services.deployment_clients import (
		_deployable_clients,
		derive_partner,
		derive_partner_client,
	)

	projects = frappe.get_all(
		"Project",
		filters={"custom_crm_deal": crm_deal_name},
		fields=["name", "customer", "icorp_client_id"],
	)
	eligible = [p for p in projects if not p.customer or p.customer == customer_name]
	if not eligible:
		return

	own = [c for c in _deployable_clients(customer_name) if c["group"] == "own"]
	own_client = own[0]["name"] if len(own) == 1 else None

	for project in eligible:
		values: dict = {}
		if not project.customer:
			values["customer"] = customer_name
		if own_client and not project.icorp_client_id:
			values["icorp_client_id"] = own_client
			partner = derive_partner(own_client)
			partner_client = derive_partner_client(own_client)
			if partner:
				values["partner_customer"] = partner
			if partner_client:
				values["partner_icorp_client_id"] = partner_client
		if values:
			set_value_tracked("Project", project.name, values)


def on_project_customer_set(doc: Any, method: str | None = None) -> None:
	"""Project on_update hook: a deployer set Customer on a Deployment Project of a CRM Deal.

	Acts only when ``customer`` changed to a set value on an existing Deployment
	Project that belongs to a CRM Deal. Brand-new Projects are skipped. Failures are
	logged and never block the Project save.

	- Deal has no Client: apply_deal_customer (fills the deal, blank sibling
	  Projects, and the organization).
	- Deal's Client equals the Project's Customer: nothing to do.
	- Deal's Client differs: the deal and its Projects are left unchanged. A Comment
	  is added to the deal.
	"""
	if not (
		doc.project_type == "Deployment"
		and doc.custom_crm_deal
		and doc.customer
		and doc.has_value_changed("customer")
	):
		return
	if doc.get_doc_before_save() is None:
		return

	run_guarded(
		f"Customer change on Project {doc.name} failed",
		_propagate_project_customer,
		doc.name,
		doc.custom_crm_deal,
		doc.customer,
	)


def _propagate_project_customer(project_name: str, crm_deal_name: str, customer_name: str) -> None:
	"""Decide what a Project's new Customer does to its deal (see on_project_customer_set)."""
	deal_client = frappe.db.get_value("CRM Deal", crm_deal_name, "custom_customer")
	if not deal_client:
		apply_deal_customer(crm_deal_name, customer_name)
		return
	if deal_client == customer_name:
		return
	project = frappe.get_doc("Project", project_name)
	_comment_project_customer_mismatch(project, deal_client)


def _comment_project_customer_mismatch(project: Any, deal_client: str) -> None:
	"""Comment on the CRM Deal about a Project whose Customer differs from the deal's Client.
	Inserts the Comment only; neither the deal nor the Project is saved."""
	deal_name = project.custom_crm_deal

	project_link = frappe.utils.get_link_to_form("Project", project.name)
	new_customer_link = frappe.utils.get_link_to_form("Customer", project.customer)
	deal_customer_link = frappe.utils.get_link_to_form("Customer", deal_client)
	content = (
		f"Deployment {project_link} was given Customer {new_customer_link}, "
		f"but this deal's Client is {deal_customer_link}. Neither was changed."
	)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "CRM Deal",
			"reference_name": deal_name,
			"content": content,
		}
	).insert(ignore_permissions=True)


def _learn_org_customer(org_name: str, customer_name: str, crm_deal_name: str) -> None:
	"""Learn a deal-confirmed Customer onto its CRM Organization.

	- Blank org link: set it (source "Deal"); on_org_customer_set then backfills
	  other blank Won deals on the org.
	- Same link: no-op.
	- Different link: the org maps to several Customers. Clear the link, mark the
	  org "Deal-level only" (never trusted again), and leave a Comment on the deal.
	"""
	org = frappe.get_doc("CRM Organization", org_name)
	if org.custom_resolution_mode == DEAL_LEVEL_ONLY:
		return

	if not org.custom_customer:
		org.flags.customer_assignment_source = "Deal"
		org.custom_customer = customer_name
		org.save(ignore_permissions=True)
		return

	if org.custom_customer == customer_name:
		return

	previous = org.custom_customer
	org.custom_customer = None
	org.custom_resolution_mode = DEAL_LEVEL_ONLY
	org.custom_customer_assignment_source = None
	org.save(ignore_permissions=True)

	frappe.logger(_LOG).warning(
		f"CRM Organization {org_name} set to '{DEAL_LEVEL_ONLY}': deal {crm_deal_name} resolved to "
		f"'{customer_name}' but organization was linked to '{previous}'"
	)

	org_link = frappe.utils.get_link_to_form("CRM Organization", org_name)
	new_customer_link = frappe.utils.get_link_to_form("Customer", customer_name)
	previous_customer_link = frappe.utils.get_link_to_form("Customer", previous)

	# add_comment only inserts a Comment doc; it does not save the deal.
	frappe.get_doc("CRM Deal", crm_deal_name).add_comment(
		"Comment",
		f"Customer conflict: this deal resolved to {new_customer_link}, but {org_link} was already "
		f"linked to {previous_customer_link}. The organization has been set to {DEAL_LEVEL_ONLY}, "
		"so future deals here need their Customer set individually. No action needed unless this "
		"looks wrong.",
	)


def on_deal_customer_set(doc: Any, method: str | None = None) -> None:
	"""CRM Deal on_update hook: a human set Client on a deal that is already Won.

	Fires only when the deal was Won before this save, custom_customer goes from
	blank to set. The Won transition itself is handled by deal.on_update.
	"""
	if doc.status != "Won":
		return
	before = doc.get_doc_before_save()
	if not before or before.status != "Won":
		return
	if not doc.has_value_changed("custom_customer") or not doc.custom_customer:
		return
	if before.custom_customer:
		return
	run_guarded(
		f"Customer propagation failed for CRM Deal {doc.name}",
		apply_deal_customer,
		doc.name,
		doc.custom_customer,
	)


def on_deal_status_leaves_won(doc: Any, method: str | None = None) -> None:
	"""CRM Deal on_update hook: the deal moved from Won to another status.

	Adds one Comment on the deal listing the Deployments created from it. Projects are
	not changed. Fires only on the Won -> other transition, so one comment per transition.
	"""
	if doc.status == "Won":
		return
	before = doc.get_doc_before_save()
	if not before or before.status != "Won":
		return

	project_names = frappe.get_all("Project", filters={"custom_crm_deal": doc.name}, pluck="name")
	project_links = [frappe.utils.get_link_to_form("Project", n) for n in project_names]
	if not project_links:
		outcome = "No deployments had been created from it."
	elif len(project_links) == 1:
		outcome = f"Deployment {project_links[0]} already exists and was not changed."
	else:
		outcome = f"Deployments {', '.join(project_links)} already exist and were not changed."
	content = f"Deal is no longer Won in HubSpot (now {doc.status}). {outcome}"
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "CRM Deal",
			"reference_name": doc.name,
			"content": content,
		}
	).insert(ignore_permissions=True)
