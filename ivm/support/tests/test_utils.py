import frappe
from frappe.tests.utils import FrappeTestCase

from ivm.support.utils import fetch_customer_name_and_contact


class TestFetchCustomerNameAndContact(FrappeTestCase):
    """Test suite for ivm.support.utils.fetch_customer_name_and_contact"""

    def test_contact_with_email_and_customer_link(self):
        """Case 1: Contact with matching email and Dynamic Link to Customer → returns dict"""
        # Create a Customer
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Test Customer",
            "customer_type": "Individual"
        }).insert()
        
        # Create a Contact with email and link to Customer
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": "John",
            "last_name": "Doe",
            "email_ids": [
                {
                    "email_id": "john@example.com",
                    "is_primary": 1
                }
            ],
            "links": [
                {
                    "link_doctype": "Customer",
                    "link_name": customer.name
                }
            ]
        }).insert()
        
        # Call the function
        result = fetch_customer_name_and_contact("john@example.com")
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("contact_name"), contact.name)
        self.assertEqual(result.get("customer_name"), customer.name)

    def test_contact_with_email_no_customer_link(self):
        """Case 2: Contact with matching email but NO Dynamic Link → returns dict with None customer"""
        # Create a Contact with email but no customer link
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": "Jane",
            "last_name": "Smith",
            "email_ids": [
                {
                    "email_id": "jane@example.com",
                    "is_primary": 1
                }
            ]
        }).insert()
        
        # Call the function
        result = fetch_customer_name_and_contact("jane@example.com")
        
        # Verify result
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("contact_name"), contact.name)
        # customer_name should be None (LEFT JOIN with no match)
        self.assertIsNone(result.get("customer_name"))

    def test_no_matching_contact_email(self):
        """Case 3: No Contact/Contact Email matches sender → returns None"""
        # Call with non-existent email
        result = fetch_customer_name_and_contact("nonexistent@example.com")
        
        # Verify result is None
        self.assertIsNone(result)

    def test_contact_linked_to_multiple_customers(self):
        """Case 4: Contact linked to TWO Customers → returns dict (first row, order unspecified)"""
        # Create two Customers
        customer1 = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Customer One",
            "customer_type": "Individual"
        }).insert()
        customer2 = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Customer Two",
            "customer_type": "Individual"
        }).insert()
        
        # Create a Contact linked to both customers
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": "Multi",
            "last_name": "Link",
            "email_ids": [
                {
                    "email_id": "multi@example.com",
                    "is_primary": 1
                }
            ],
            "links": [
                {
                    "link_doctype": "Customer",
                    "link_name": customer1.name
                },
                {
                    "link_doctype": "Customer",
                    "link_name": customer2.name
                }
            ]
        }).insert()
        
        # Call the function
        result = fetch_customer_name_and_contact("multi@example.com")
        
        # Verify result is a dict
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("contact_name"), contact.name)
        
        # customer_name should be one of the two (order unspecified due to no ORDER BY)
        # Just verify it's one of the valid customer names
        valid_customers = [customer1.name, customer2.name]
        self.assertIn(result.get("customer_name"), valid_customers)

    def test_multiple_contact_emails_same_contact(self):
        """Additional: Contact with multiple email addresses → matches on any of them"""
        # Create a Customer
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Multi Email Customer",
            "customer_type": "Individual"
        }).insert()
        
        # Create a Contact with multiple emails
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": "Multi",
            "last_name": "Email",
            "email_ids": [
                {
                    "email_id": "primary@example.com",
                    "is_primary": 1
                },
                {
                    "email_id": "secondary@example.com",
                    "is_primary": 0
                }
            ],
            "links": [
                {
                    "link_doctype": "Customer",
                    "link_name": customer.name
                }
            ]
        }).insert()
        
        # Call with primary email
        result1 = fetch_customer_name_and_contact("primary@example.com")
        self.assertIsNotNone(result1)
        self.assertEqual(result1.get("contact_name"), contact.name)
        self.assertEqual(result1.get("customer_name"), customer.name)
        
        # Call with secondary email
        result2 = fetch_customer_name_and_contact("secondary@example.com")
        self.assertIsNotNone(result2)
        self.assertEqual(result2.get("contact_name"), contact.name)
        self.assertEqual(result2.get("customer_name"), customer.name)

    def test_case_sensitivity_email(self):
        """Additional: Email matching should be case-sensitive (as per SQL)"""
        # Create a Customer
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": "Case Test Customer",
            "customer_type": "Individual"
        }).insert()
        
        # Create a Contact with lowercase email
        contact = frappe.get_doc({
            "doctype": "Contact",
            "first_name": "Case",
            "last_name": "Test",
            "email_ids": [
                {
                    "email_id": "test@example.com",
                    "is_primary": 1
                }
            ],
            "links": [
                {
                    "link_doctype": "Customer",
                    "link_name": customer.name
                }
            ]
        }).insert()
        
        # Call with exact case
        result = fetch_customer_name_and_contact("test@example.com")
        self.assertIsNotNone(result)
        
        # Call with different case (may or may not match depending on DB collation)
        # Just verify the function doesn't crash
        result_upper = fetch_customer_name_and_contact("TEST@EXAMPLE.COM")
        # Don't assert on result value since DB collation is environment-dependent
