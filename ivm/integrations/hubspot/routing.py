"""Single routing table mapping a HubSpot object type ID to its sync target.

Used by both the webhook receiver and the scheduled reconciliation job, so a
HubSpot change — however it's noticed — always ends up in the same place:
"does this object type need syncing, does this specific record pass the
gate, and if so, enqueue (or skip, or follow-up) its sync job."

Unlike the old per-``subscriptionType`` routing table, any event on a known
object type means "re-sync that record" — the sync functions always re-read
the current HubSpot state rather than acting on the specific property or
association that changed.
"""

from collections.abc import Callable
from typing import NamedTuple

import frappe

from ivm.integrations.hubspot.constants import (
	BIN_TYPE_ID,
	COMPANY_TYPE_ID,
	CONTACT_TYPE_ID,
	DEAL_TYPE_ID,
	DEPLOYMENT_SITE_TYPE_ID,
	ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID,
	HUBSPOT_COMPANY_ID_FIELD,
	HUBSPOT_CONTACT_ID_FIELD,
	MACHINE_TYPE_TO_CHILD_TABLE,
)
from ivm.integrations.hubspot.sync_utils import enqueue_sync

_HANDLER_PREFIX = "ivm.integrations.hubspot"


class SyncTarget(NamedTuple):
	"""Where a HubSpot object type's sync job goes, and the gate that
	decides whether a given record is worth enqueueing at all.
	"""

	method: str
	kwargs_builder: Callable[[str], dict]
	gate: Callable[[str], bool]


def _always(_object_id: str) -> bool:
	"""Gate that never drops a record."""
	return True


def _contact_is_known(object_id: str) -> bool:
	"""Only sync contacts that already exist locally (i.e. are linked to a deal).

	Frappe has no use for HubSpot contacts that aren't attached to a deal —
	dropping them here filters out enrichment and third-party-integration
	traffic (e.g. ZoomInfo) before it becomes a job.
	"""
	return bool(frappe.db.exists("Contact", {HUBSPOT_CONTACT_ID_FIELD: object_id}))


def _company_is_known(object_id: str) -> bool:
	"""Only sync companies that already exist locally (i.e. are linked to a deal)."""
	return bool(frappe.db.exists("CRM Organization", {HUBSPOT_COMPANY_ID_FIELD: object_id}))


def _id_kwarg(key: str) -> Callable[[str], dict]:
	"""Return a kwargs builder that maps an object id to *key*."""

	def _builder(object_id: str) -> dict:
		return {key: object_id}

	return _builder


def _machine_kwargs(machine_type_id: str) -> Callable[[str], dict]:
	"""Return a kwargs builder for a specific machine type ID."""

	def _builder(object_id: str) -> dict:
		return {"machine_type_id": machine_type_id, "hubspot_machine_id": object_id}

	return _builder


def _engagement_kwargs(engagement_type: str) -> Callable[[str], dict]:
	"""Return a kwargs builder for a specific engagement type name."""

	def _builder(object_id: str) -> dict:
		return {"engagement_type": engagement_type, "engagement_id": object_id}

	return _builder


SYNC_TARGETS: dict[str, SyncTarget] = {
	DEAL_TYPE_ID: SyncTarget(
		method=f"{_HANDLER_PREFIX}.deal_handler.sync_deal",
		kwargs_builder=_id_kwarg("hubspot_deal_id"),
		gate=_always,
	),
	CONTACT_TYPE_ID: SyncTarget(
		method=f"{_HANDLER_PREFIX}.contact_handler.sync_contact",
		kwargs_builder=_id_kwarg("hubspot_contact_id"),
		gate=_contact_is_known,
	),
	COMPANY_TYPE_ID: SyncTarget(
		method=f"{_HANDLER_PREFIX}.company_handler.sync_company",
		kwargs_builder=_id_kwarg("hubspot_company_id"),
		gate=_company_is_known,
	),
	DEPLOYMENT_SITE_TYPE_ID: SyncTarget(
		method=f"{_HANDLER_PREFIX}.deployment_site_handler.sync_site",
		kwargs_builder=_id_kwarg("hubspot_site_id"),
		gate=_always,
	),
	BIN_TYPE_ID: SyncTarget(
		method=f"{_HANDLER_PREFIX}.deployment_site_handler.sync_bin",
		kwargs_builder=_id_kwarg("hubspot_bin_id"),
		gate=_always,
	),
}

for _machine_type_id in MACHINE_TYPE_TO_CHILD_TABLE:
	SYNC_TARGETS[_machine_type_id] = SyncTarget(
		method=f"{_HANDLER_PREFIX}.deployment_site_handler.sync_machine",
		kwargs_builder=_machine_kwargs(_machine_type_id),
		gate=_always,
	)

for _engagement_type_id, _engagement_type in ENGAGEMENT_TYPE_BY_OBJECT_TYPE_ID.items():
	SYNC_TARGETS[_engagement_type_id] = SyncTarget(
		method=f"{_HANDLER_PREFIX}.activity_handler.sync_engagement",
		kwargs_builder=_engagement_kwargs(_engagement_type),
		gate=_always,
	)


def route(object_type_id: str, object_id: str) -> str:
	"""Dispatch a HubSpot object change to its sync job.

	Returns ``"enqueued"``, ``"skipped"`` (a job for this record is already
	in flight), ``"dropped"`` (the gate rejected it), or ``"unhandled"`` (no
	sync target is registered for this object type).
	"""
	target = SYNC_TARGETS.get(object_type_id)
	if target is None:
		return "unhandled"

	object_id = str(object_id)
	if not target.gate(object_id):
		return "dropped"

	kwargs = target.kwargs_builder(object_id)
	result = enqueue_sync(target.method, object_type_id, object_id, **kwargs)
	return "skipped" if result == "skipped" else "enqueued"
