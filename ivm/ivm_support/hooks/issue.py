from ivm.ivm_support.services.ticket_manager import create_linked_ticket_on_insert


def after_insert(doc, method=None):
    """Hook to auto-create linked ticket when Issue is created"""
    create_linked_ticket_on_insert(doc)
