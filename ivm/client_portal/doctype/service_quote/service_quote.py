"""
Service Quote doctype controller.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, today

from ivm.client_portal.utils.signers import get_signer_row_for_user


class ServiceQuote(Document):
    def before_insert(self):
        """Default valid_until to 30 days from creation if not already set."""
        if not self.valid_until:
            self.valid_until = add_days(today(), 30)

    def validate(self):
        """Recompute grand_total and item amounts, resolve customer/organization."""
        self._compute_item_amounts()
        self._compute_grand_total()
        self._resolve_customer_or_organization()

    def _compute_item_amounts(self):
        """Ensure each item's amount = qty * rate."""
        for item in self.items or []:
            item.amount = (item.qty or 0) * (item.rate or 0)

    def _compute_grand_total(self):
        """Sum all item amounts into grand_total."""
        self.grand_total = sum(item.amount or 0 for item in self.items or [])

    def _resolve_customer_or_organization(self):
        """
        When a CRM Deal is first linked (or the link changes), resolve which
        of customer / crm_organization should be set based on the deal's
        custom_deal_type ("New Business" / "Existing Business" — same
        convention as ivm/deployments/event_handlers/deal.py).

        Only re-derives from the live CRM Deal when crm_deal itself has
        changed — not on every save. This prevents a submitted quote's
        already-validated customer/crm_organization from being silently
        overwritten by drifted Deal data on an unrelated resave, which
        would trip _validate_update_after_submit on fields the user never
        touched.

        Regardless of whether re-derivation runs, the mutual-exclusivity
        invariant (exactly one of customer / crm_organization) is always
        enforced.
        """
        if self.crm_deal and self.has_value_changed("crm_deal"):
            deal_type = frappe.db.get_value("CRM Deal", self.crm_deal, "custom_deal_type")
            if deal_type == "New Business":
                self.crm_organization = frappe.db.get_value("CRM Deal", self.crm_deal, "organization")
                self.customer = None
            elif deal_type == "Existing Business":
                self.customer = frappe.db.get_value("CRM Deal", self.crm_deal, "custom_customer")
                self.crm_organization = None

        if bool(self.customer) == bool(self.crm_organization):
            frappe.throw(
                "Exactly one of Customer or CRM Organization must be set (not both, not neither)."
            )


def has_website_permission(doc, ptype, user, verbose=False):
    """
    Check if user has website permission to view this Service Quote.

    Only submitted quotes (docstatus == 1) are visible on the portal —
    draft quotes may already have signers added during preparation, but
    must not be accessible to clients until the rep submits.

    Delegates to get_signer_row_for_user — user must have a Contact linked
    to their User record, and that Contact must appear in the quote's
    signers list.
    """
    if user == "Guest":
        return False
    if doc.docstatus != 1:
        return False
    return get_signer_row_for_user(doc, user) is not None
