"""Integration tests for ivm.deployments.event_handlers.deal_notes"""

import time

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.event_handlers.deal_notes import (
    add_note,
    delete_note,
    edit_note,
    get_notes,
)


def _ensure_deal_status(status):
    if not frappe.db.exists("CRM Deal Status", status):
        frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
            ignore_permissions=True,
        )


def _make_deal():
    uid = frappe.generate_hash(length=8)
    _ensure_deal_status("Qualification")
    return frappe.get_doc({
        "doctype": "CRM Deal",
        "status": "Qualification",
        "custom_hubspot_deal_name": f"Test Deal {uid}",
    }).insert(ignore_permissions=True)


class TestGetNotes(ERPNextTestSuite):
    """get_notes returns FCRM Notes linked to a CRM Deal, newest first."""

    def test_returns_notes_newest_first(self):
        """Create 2+ notes with distinct modified times, verify newest-first order."""
        deal = _make_deal()
        
        # Create first note
        note1_name = add_note(deal.name, "First Note", "Content 1")
        note1 = frappe.get_doc("FCRM Note", note1_name)
        
        # Small delay to ensure distinct modified timestamps
        time.sleep(0.1)
        
        # Create second note
        note2_name = add_note(deal.name, "Second Note", "Content 2")
        note2 = frappe.get_doc("FCRM Note", note2_name)
        
        # Small delay
        time.sleep(0.1)
        
        # Create third note
        note3_name = add_note(deal.name, "Third Note", "Content 3")
        
        # Get notes and verify order (newest first)
        notes = get_notes(deal.name)
        self.assertEqual(len(notes), 3)
        self.assertEqual(notes[0]["name"], note3_name)
        self.assertEqual(notes[1]["name"], note2_name)
        self.assertEqual(notes[2]["name"], note1_name)

    def test_returns_empty_list_for_deal_with_no_notes(self):
        """A CRM Deal with zero notes returns empty list."""
        deal = _make_deal()
        notes = get_notes(deal.name)
        self.assertEqual(notes, [])

    def test_excludes_notes_from_other_deals(self):
        """Notes linked to a different deal are excluded."""
        deal1 = _make_deal()
        deal2 = _make_deal()
        
        # Add notes to both deals
        note1_name = add_note(deal1.name, "Deal 1 Note", "Content for deal 1")
        note2_name = add_note(deal2.name, "Deal 2 Note", "Content for deal 2")
        
        # Get notes for deal1 — should only include note1
        notes_deal1 = get_notes(deal1.name)
        self.assertEqual(len(notes_deal1), 1)
        self.assertEqual(notes_deal1[0]["name"], note1_name)
        
        # Get notes for deal2 — should only include note2
        notes_deal2 = get_notes(deal2.name)
        self.assertEqual(len(notes_deal2), 1)
        self.assertEqual(notes_deal2[0]["name"], note2_name)


class TestAddNote(ERPNextTestSuite):
    """add_note creates a new FCRM Note linked to a CRM Deal."""

    def test_creates_note_with_correct_fields(self):
        """add_note creates FCRM Note with correct reference_doctype, reference_docname, title, content."""
        deal = _make_deal()
        title = "Test Note Title"
        content = "Test note content here"
        
        note_name = add_note(deal.name, title, content)
        
        # Verify note was created
        self.assertTrue(frappe.db.exists("FCRM Note", note_name))
        
        # Reload and verify fields
        note = frappe.get_doc("FCRM Note", note_name)
        self.assertEqual(note.reference_doctype, "CRM Deal")
        self.assertEqual(note.reference_docname, deal.name)
        self.assertEqual(note.title, title)
        self.assertEqual(note.content, content)

    def test_returns_note_name(self):
        """add_note returns the created note's name."""
        deal = _make_deal()
        note_name = add_note(deal.name, "Title", "Content")
        
        # Verify it's a non-empty string and the doc exists
        self.assertIsInstance(note_name, str)
        self.assertTrue(len(note_name) > 0)
        self.assertTrue(frappe.db.exists("FCRM Note", note_name))


class TestEditNote(ERPNextTestSuite):
    """edit_note updates an existing FCRM Note."""

    def test_updates_title_and_content(self):
        """edit_note updates both title and content fields."""
        deal = _make_deal()
        note_name = add_note(deal.name, "Original Title", "Original content")
        
        new_title = "Updated Title"
        new_content = "Updated content here"
        
        edit_note(note_name, new_title, new_content)
        
        # Reload and verify both fields updated
        note = frappe.get_doc("FCRM Note", note_name)
        self.assertEqual(note.title, new_title)
        self.assertEqual(note.content, new_content)

    def test_preserves_reference_fields(self):
        """edit_note preserves reference_doctype and reference_docname."""
        deal = _make_deal()
        note_name = add_note(deal.name, "Title", "Content")
        
        edit_note(note_name, "New Title", "New Content")
        
        note = frappe.get_doc("FCRM Note", note_name)
        self.assertEqual(note.reference_doctype, "CRM Deal")
        self.assertEqual(note.reference_docname, deal.name)


class TestDeleteNote(ERPNextTestSuite):
    """delete_note removes an FCRM Note."""

    def test_deletes_existing_note(self):
        """delete_note removes the note from the database."""
        deal = _make_deal()
        note_name = add_note(deal.name, "Title", "Content")
        
        # Verify note exists
        self.assertTrue(frappe.db.exists("FCRM Note", note_name))
        
        # Delete it
        delete_note(note_name)
        
        # Verify it's gone
        self.assertFalse(frappe.db.exists("FCRM Note", note_name))

    def test_noop_on_nonexistent_note(self):
        """delete_note silently succeeds on nonexistent note (frappe.delete_doc behavior)."""
        nonexistent_name = "FCRM-NOTE-DOES-NOT-EXIST-12345"
        
        # Should not raise; frappe.delete_doc silently succeeds
        delete_note(nonexistent_name)
