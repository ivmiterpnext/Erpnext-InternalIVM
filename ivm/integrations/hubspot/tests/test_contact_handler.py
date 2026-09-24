"""Tests for ivm.integrations.hubspot.contact_handler"""

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from ivm.integrations.hubspot.contact_handler import (
	_normalize_primary,
	_sanitize_phone,
	upsert_contact,
)


class TestSanitizePhone(FrappeTestCase):
	"""_sanitize_phone pure function"""

	def test_strips_formatting_chars(self):
		"""Phone with formatting chars is stripped to digits and allowed chars."""
		phone, ext = _sanitize_phone("+1 (555) 123-4567")
		self.assertEqual(phone, "+1 (555) 123-4567")
		self.assertEqual(ext, "")

	def test_extracts_ext_suffix(self):
		"""Extension suffix 'ext 99' is extracted separately."""
		phone, ext = _sanitize_phone("555-1234 ext 99")
		self.assertEqual(phone, "555-1234")
		self.assertEqual(ext, "99")

	def test_extracts_x_suffix(self):
		"""Extension suffix 'x99' is extracted separately."""
		phone, ext = _sanitize_phone("555-1234 x99")
		self.assertEqual(phone, "555-1234")
		self.assertEqual(ext, "99")

	def test_empty_string_returns_empty_tuple(self):
		"""Empty string returns ('', '')."""
		phone, ext = _sanitize_phone("")
		self.assertEqual(phone, "")
		self.assertEqual(ext, "")

	def test_none_returns_empty_tuple(self):
		"""None input returns ('', '')."""
		phone, ext = _sanitize_phone(None)
		self.assertEqual(phone, "")
		self.assertEqual(ext, "")

	def test_truncates_to_20_chars(self):
		"""Phone longer than 20 chars is truncated."""
		long_phone = "1234567890123456789012345"  # 25 chars
		phone, ext = _sanitize_phone(long_phone)
		self.assertEqual(len(phone), 20)
		self.assertEqual(phone, "12345678901234567890")
		self.assertEqual(ext, "")

	def test_whitespace_only_returns_empty(self):
		"""Whitespace-only string returns ('', '')."""
		phone, ext = _sanitize_phone("   ")
		self.assertEqual(phone, "")
		self.assertEqual(ext, "")


class TestNormalizePrimary(FrappeTestCase):
	"""_normalize_primary child table normalization"""

	def test_preferred_value_wins_primary_flag(self):
		"""When preferred value is present, exactly one row has primary=1."""
		rows = [
			MagicMock(email_id="old@example.com"),
			MagicMock(email_id="new@example.com"),
		]
		rows[0].get = MagicMock(return_value="old@example.com")
		rows[1].get = MagicMock(return_value="new@example.com")
		_normalize_primary(rows, "email_id", "is_primary", "new@example.com")
		rows[0].set.assert_called_with("is_primary", 0)
		rows[1].set.assert_called_with("is_primary", 1)

	def test_first_row_gets_primary_when_no_preferred(self):
		"""When no preferred value, first row gets primary flag."""
		rows = [
			MagicMock(email_id="first@example.com"),
			MagicMock(email_id="second@example.com"),
		]
		rows[0].get = MagicMock(return_value="first@example.com")
		rows[1].get = MagicMock(return_value="second@example.com")
		_normalize_primary(rows, "email_id", "is_primary", "")
		rows[0].set.assert_called_with("is_primary", 1)
		rows[1].set.assert_called_with("is_primary", 0)

	def test_already_flagged_row_wins_when_no_preferred(self):
		"""When no preferred value, already-flagged row keeps primary."""
		rows = [
			MagicMock(email_id="first@example.com"),
			MagicMock(email_id="second@example.com"),
		]
		rows[0].get = MagicMock(side_effect=lambda key: "first@example.com" if key == "email_id" else None)
		rows[1].get = MagicMock(side_effect=lambda key: "second@example.com" if key == "email_id" else 1)
		_normalize_primary(rows, "email_id", "is_primary", "")
		rows[0].set.assert_called_with("is_primary", 0)
		rows[1].set.assert_called_with("is_primary", 1)

	def test_empty_rows_list_is_noop(self):
		"""Empty rows list does not raise."""
		_normalize_primary([], "email_id", "is_primary", "test@example.com")

	def test_self_heals_duplicate_primary_state(self):
		"""Multiple rows with primary=1 are collapsed to one."""
		rows = [
			MagicMock(email_id="first@example.com"),
			MagicMock(email_id="second@example.com"),
		]
		rows[0].get = MagicMock(return_value="first@example.com")
		rows[1].get = MagicMock(return_value="second@example.com")
		_normalize_primary(rows, "email_id", "is_primary", "second@example.com")
		rows[0].set.assert_called_with("is_primary", 0)
		rows[1].set.assert_called_with("is_primary", 1)


class TestUpsertContactUpdate(FrappeTestCase):
	"""upsert_contact update path (existing contact)"""

	def test_updates_existing_contact_by_hubspot_id(self):
		"""Existing contact found by hubspot_id is updated and saved."""
		existing_doc = MagicMock()
		existing_doc.doctype = "Contact"
		existing_doc.name = "Contact-001"
		existing_doc.get = MagicMock(return_value=[])

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.save_doc") as mock_save:
				with patch("ivm.integrations.hubspot.contact_handler.frappe.get_meta") as mock_meta:
					mock_find.return_value = existing_doc
					mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

					result = upsert_contact(
						{"first_name": "John", "email": "john@example.com"},
						hubspot_contact_id="hs123",
					)

					self.assertEqual(result, "Contact-001")
					mock_save.assert_called_once()

	def test_updates_existing_contact_by_email_fallback(self):
		"""Existing contact found by email (no hubspot_id match) is updated."""
		existing_doc = MagicMock()
		existing_doc.doctype = "Contact"
		existing_doc.name = "Contact-002"
		existing_doc.get = MagicMock(return_value=[])

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.save_doc") as mock_save:
				with patch("ivm.integrations.hubspot.contact_handler.frappe.get_meta") as mock_meta:
					mock_find.return_value = existing_doc
					mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

					result = upsert_contact(
						{"first_name": "Jane", "email": "jane@example.com"},
						hubspot_contact_id=None,
					)

					self.assertEqual(result, "Contact-002")
					mock_save.assert_called_once()

	def test_skips_invalid_link_field_target(self):
		"""Link field with invalid target value logs warning and skips field."""
		existing_doc = MagicMock()
		existing_doc.doctype = "Contact"
		existing_doc.name = "Contact-003"
		existing_doc.get = MagicMock(return_value=[])

		link_field = MagicMock()
		link_field.fieldtype = "Link"
		link_field.options = "Company"

		meta = MagicMock()
		meta.get_field = MagicMock(side_effect=lambda key: link_field if key == "custom_company" else None)

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.save_doc"):
				with patch("ivm.integrations.hubspot.contact_handler.frappe.get_meta") as mock_meta:
					with patch("ivm.integrations.hubspot.contact_handler.frappe.db.exists") as mock_exists:
						with patch("ivm.integrations.hubspot.contact_handler.frappe.logger") as mock_logger:
							mock_logger_instance = MagicMock()
							mock_logger.return_value = mock_logger_instance
							mock_find.return_value = existing_doc
							mock_meta.return_value = meta
							mock_exists.return_value = False

							upsert_contact(
								{
									"first_name": "Bob",
									"email": "bob@example.com",
									"custom_company": "NonExistent Corp",
								},
								hubspot_contact_id="hs456",
							)

							mock_logger_instance.warning.assert_called()
							existing_doc.set.assert_not_called()


class TestUpsertContactInsert(FrappeTestCase):
	"""upsert_contact insert path (new contact)"""

	def test_creates_new_contact_with_email_and_phone(self):
		"""New contact with email + phone creates child table rows correctly."""
		new_doc = MagicMock()
		new_doc.doctype = "Contact"
		new_doc.name = "Contact-New-001"
		new_doc.append = MagicMock()

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.frappe.new_doc") as mock_new:
				with patch("ivm.integrations.hubspot.contact_handler.insert_with_retry"):
					with patch("ivm.integrations.hubspot.contact_handler.frappe.db.savepoint"):
						with patch("ivm.integrations.hubspot.contact_handler.frappe.db.commit"):
							with patch("ivm.integrations.hubspot.contact_handler.frappe.logger"):
								with patch(
									"ivm.integrations.hubspot.contact_handler.frappe.get_meta"
								) as mock_meta:
									mock_find.return_value = None
									mock_new.return_value = new_doc
									mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

									upsert_contact(
										{
											"first_name": "Alice",
											"email": "alice@example.com",
											"mobile_no": "+1 (555) 123-4567",
											"phone": "555-9999",
										},
										hubspot_contact_id="hs789",
									)

									self.assertEqual(new_doc.first_name, "Alice")
									self.assertEqual(new_doc.company_name, "")
									new_doc.append.assert_called()

	def test_duplicate_entry_error_falls_back_to_update(self):
		"""DuplicateEntryError on insert rolls back and finds existing contact."""
		new_doc = MagicMock()
		new_doc.doctype = "Contact"
		new_doc.name = "Contact-Dup"

		existing_doc = MagicMock()
		existing_doc.doctype = "Contact"
		existing_doc.name = "Contact-Found"
		existing_doc.get = MagicMock(return_value=[])

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.frappe.new_doc") as mock_new:
				with patch("ivm.integrations.hubspot.contact_handler.insert_with_retry") as mock_insert:
					with patch("ivm.integrations.hubspot.contact_handler.frappe.db.savepoint"):
						with patch("ivm.integrations.hubspot.contact_handler.frappe.db.rollback"):
							with patch("ivm.integrations.hubspot.contact_handler.save_doc") as mock_save:
								with patch("ivm.integrations.hubspot.contact_handler.frappe.logger"):
									with patch(
										"ivm.integrations.hubspot.contact_handler.frappe.get_meta"
									) as mock_meta:
										mock_find.side_effect = [None, existing_doc]
										mock_new.return_value = new_doc
										mock_insert.side_effect = Exception("frappe.DuplicateEntryError")
										mock_meta.return_value = MagicMock(
											get_field=MagicMock(return_value=None)
										)

										# Manually raise DuplicateEntryError
										import frappe

										mock_insert.side_effect = frappe.DuplicateEntryError()

										result = upsert_contact(
											{"first_name": "Charlie", "email": "charlie@example.com"},
											hubspot_contact_id="hs999",
										)

										self.assertEqual(result, "Contact-Found")
										mock_save.assert_called_once()

	def test_duplicate_error_not_found_after_retry_returns_none(self):
		"""DuplicateEntryError raised but contact still not found returns None."""
		new_doc = MagicMock()
		new_doc.doctype = "Contact"
		new_doc.name = "Contact-Lost"

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.frappe.new_doc") as mock_new:
				with patch("ivm.integrations.hubspot.contact_handler.insert_with_retry") as mock_insert:
					with patch("ivm.integrations.hubspot.contact_handler.frappe.db.savepoint"):
						with patch("ivm.integrations.hubspot.contact_handler.frappe.db.rollback"):
							with patch("ivm.integrations.hubspot.contact_handler.frappe.logger"):
								with patch(
									"ivm.integrations.hubspot.contact_handler.frappe.get_meta"
								) as mock_meta:
									mock_find.return_value = None
									mock_new.return_value = new_doc
									import frappe

									mock_insert.side_effect = frappe.DuplicateEntryError()
									mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

									result = upsert_contact(
										{"first_name": "David", "email": "david@example.com"},
										hubspot_contact_id="hs111",
									)

									self.assertIsNone(result)

	def test_query_deadlock_error_reraises(self):
		"""QueryDeadlockError on insert rolls back and re-raises."""
		new_doc = MagicMock()
		new_doc.doctype = "Contact"
		new_doc.name = "Contact-Deadlock"

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.frappe.new_doc") as mock_new:
				with patch("ivm.integrations.hubspot.contact_handler.insert_with_retry") as mock_insert:
					with patch("ivm.integrations.hubspot.contact_handler.frappe.db.savepoint"):
						with patch("ivm.integrations.hubspot.contact_handler.frappe.db.rollback"):
							with patch("ivm.integrations.hubspot.contact_handler.frappe.logger"):
								with patch(
									"ivm.integrations.hubspot.contact_handler.frappe.get_meta"
								) as mock_meta:
									mock_find.return_value = None
									mock_new.return_value = new_doc
									import frappe

									mock_insert.side_effect = frappe.QueryDeadlockError()
									mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

									with self.assertRaises(frappe.QueryDeadlockError):
										upsert_contact(
											{"first_name": "Eve", "email": "eve@example.com"},
											hubspot_contact_id="hs222",
										)


class TestUpsertContactEdgeCases(FrappeTestCase):
	"""upsert_contact edge cases"""

	def test_no_first_name_and_no_email_returns_none(self):
		"""Contact with no first_name AND no email returns None immediately."""
		result = upsert_contact(
			{"first_name": "", "email": "", "last_name": "Smith"},
			hubspot_contact_id="hs333",
		)
		self.assertIsNone(result)

	def test_address_props_synced_when_provided(self):
		"""When address_props provided, _sync_contact_address is called."""
		existing_doc = MagicMock()
		existing_doc.doctype = "Contact"
		existing_doc.name = "Contact-Addr"
		existing_doc.get = MagicMock(return_value=[])

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.save_doc"):
				with patch(
					"ivm.integrations.hubspot.contact_handler._sync_contact_address"
				) as mock_sync_addr:
					with patch("ivm.integrations.hubspot.contact_handler.frappe.get_meta") as mock_meta:
						mock_find.return_value = existing_doc
						mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

						upsert_contact(
							{"first_name": "Frank", "email": "frank@example.com"},
							hubspot_contact_id="hs444",
							address_props={
								"address": "123 Main St",
								"city": "Springfield",
								"state": "IL",
								"country": "USA",
							},
						)

						mock_sync_addr.assert_called_once_with(
							"Contact-Addr",
							{
								"address": "123 Main St",
								"city": "Springfield",
								"state": "IL",
								"country": "USA",
							},
						)

	def test_email_only_contact_uses_email_as_first_name(self):
		"""Contact with email but no first_name uses email as first_name."""
		new_doc = MagicMock()
		new_doc.doctype = "Contact"
		new_doc.name = "Contact-Email-Only"
		new_doc.append = MagicMock()

		with patch("ivm.integrations.hubspot.contact_handler._find_existing_contact") as mock_find:
			with patch("ivm.integrations.hubspot.contact_handler.frappe.new_doc") as mock_new:
				with patch("ivm.integrations.hubspot.contact_handler.insert_with_retry"):
					with patch("ivm.integrations.hubspot.contact_handler.frappe.db.savepoint"):
						with patch("ivm.integrations.hubspot.contact_handler.frappe.db.commit"):
							with patch("ivm.integrations.hubspot.contact_handler.frappe.logger"):
								with patch(
									"ivm.integrations.hubspot.contact_handler.frappe.get_meta"
								) as mock_meta:
									mock_find.return_value = None
									mock_new.return_value = new_doc
									mock_meta.return_value = MagicMock(get_field=MagicMock(return_value=None))

									upsert_contact(
										{"first_name": "", "email": "noname@example.com"},
										hubspot_contact_id="hs555",
									)

									self.assertEqual(new_doc.first_name, "noname@example.com")
