"""
Service Quote Signer child doctype.
"""

from frappe.model.document import Document


class ServiceQuoteSigner(Document):
    # external_reference is intentionally unused/reserved for future third-party
    # e-signature vendor envelope/recipient ID integration.
    pass
