"""Integration tests for ivm.deployments.services.provision_project_from_deal"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite


class TestMasterCustomerProvisioning(ERPNextTestSuite):
    """Test that CRM Deal's custom_master_customer is carried to created Projects"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Ensure the IVM company exists (required by Project-company-default Property Setter)
        if not frappe.db.exists("Company", "IVM"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "IVM",
                "abbr": "IVM",
                "default_currency": "USD",
                "country": "United States",
            }).insert(ignore_permissions=True)
    


    def test_master_customer_carried_to_project(self):
        """Master customer from deal should be set on created project"""
        # Ensure a non-group customer group exists
        if not frappe.db.exists("Customer Group", "_Test Customer Group"):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": "_Test Customer Group",
                "is_group": 0,
            }).insert(ignore_permissions=True)
        
        # Create two customers with unique names (use method name + hash for uniqueness)
        uid = f"test1_{frappe.generate_hash(length=8)}"
        primary_customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Primary Customer {uid}",
            "customer_type": "Company",
            "customer_group": "_Test Customer Group",
        }).insert(ignore_permissions=True)

        master_customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Master Client {uid}",
            "customer_type": "Company",
            "customer_group": "_Test Customer Group",
        }).insert(ignore_permissions=True)

        # Create a CRM Deal Status (required for deal creation)
        if not frappe.db.exists("CRM Deal Status", "Won"):
            frappe.get_doc({
                "doctype": "CRM Deal Status",
                "name": "Won",
                "status": "Won",
            }).insert(ignore_permissions=True)

        # Create a CRM Deal with both customers (status not Won yet)
        deal = frappe.get_doc({
            "doctype": "CRM Deal",
            "status": "Qualification",
            "custom_customer": primary_customer.name,
            "custom_master_customer": master_customer.name,
            "custom_hubspot_deal_name": f"Deal {uid}",
        }).insert(ignore_permissions=True)

        # Create a Deployment Location linked to the deal
        location = frappe.get_doc({
            "doctype": "Deployment Location",
            "location_name": f"Test Location 1 {uid}",
            "crm_deal": deal.name,
        }).insert(ignore_permissions=True)
        
        # Now mark the deal as Won (after locations are linked)
        deal.status = "Won"
        deal.save(ignore_permissions=True)

        # Verify the created project has the master customer
        projects = frappe.db.get_list(
            "Project",
            filters={"customer": primary_customer.name, "project_type": "Deployment"},
            fields=["name", "custom_master_customer"]
        )
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["custom_master_customer"], master_customer.name)

    def test_no_master_customer_leaves_field_empty(self):
        """Project should have empty custom_master_customer when deal has none"""
        # Ensure a non-group customer group exists
        if not frappe.db.exists("Customer Group", "_Test Customer Group"):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": "_Test Customer Group",
                "is_group": 0,
            }).insert(ignore_permissions=True)
        
        # Create a customer for the deal with unique name (use method name + hash for uniqueness)
        uid = f"test2_{frappe.generate_hash(length=8)}"
        primary_customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Primary Customer 2 {uid}",
            "customer_type": "Company",
            "customer_group": "_Test Customer Group",
        }).insert(ignore_permissions=True)

        # Create a CRM Deal Status
        if not frappe.db.exists("CRM Deal Status", "Won"):
            frappe.get_doc({
                "doctype": "CRM Deal Status",
                "name": "Won",
                "status": "Won",
            }).insert(ignore_permissions=True)

        # Create a CRM Deal WITHOUT custom_master_customer (status not Won yet)
        deal = frappe.get_doc({
            "doctype": "CRM Deal",
            "status": "Qualification",
            "custom_customer": primary_customer.name,
            "custom_hubspot_deal_name": f"Deal {uid}",
        }).insert(ignore_permissions=True)

        # Create a Deployment Location
        location = frappe.get_doc({
            "doctype": "Deployment Location",
            "location_name": f"Test Location 2 {uid}",
            "crm_deal": deal.name,
        }).insert(ignore_permissions=True)
        
        # Now mark the deal as Won (after locations are linked)
        deal.status = "Won"
        deal.save(ignore_permissions=True)

        # Verify the created project has empty custom_master_customer
        projects = frappe.db.get_list(
            "Project",
            filters={"customer": primary_customer.name, "project_type": "Deployment"},
            fields=["name", "custom_master_customer"]
        )
        self.assertEqual(len(projects), 1)
        self.assertFalse(projects[0]["custom_master_customer"])

    def test_master_customer_applied_to_all_locations(self):
        """Master customer should be applied to all projects created from multiple locations"""
        # Ensure a non-group customer group exists
        if not frappe.db.exists("Customer Group", "_Test Customer Group"):
            frappe.get_doc({
                "doctype": "Customer Group",
                "customer_group_name": "_Test Customer Group",
                "is_group": 0,
            }).insert(ignore_permissions=True)
        
        # Create customers with unique names (use method name + hash for uniqueness)
        uid = f"test3_{frappe.generate_hash(length=8)}"
        primary_customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Primary Customer 3 {uid}",
            "customer_type": "Company",
            "customer_group": "_Test Customer Group",
        }).insert(ignore_permissions=True)

        master_customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": f"Master Client 2 {uid}",
            "customer_type": "Company",
            "customer_group": "_Test Customer Group",
        }).insert(ignore_permissions=True)

        # Create a CRM Deal Status
        if not frappe.db.exists("CRM Deal Status", "Won"):
            frappe.get_doc({
                "doctype": "CRM Deal Status",
                "name": "Won",
                "status": "Won",
            }).insert(ignore_permissions=True)

        # Create a CRM Deal (status not Won yet)
        deal = frappe.get_doc({
            "doctype": "CRM Deal",
            "status": "Qualification",
            "custom_customer": primary_customer.name,
            "custom_master_customer": master_customer.name,
            "custom_hubspot_deal_name": f"Deal {uid}",
        }).insert(ignore_permissions=True)

        # Create two Deployment Locations linked to the same deal
        location1 = frappe.get_doc({
            "doctype": "Deployment Location",
            "location_name": f"Test Location 3A {uid}",
            "crm_deal": deal.name,
        }).insert(ignore_permissions=True)

        location2 = frappe.get_doc({
            "doctype": "Deployment Location",
            "location_name": f"Test Location 3B {uid}",
            "crm_deal": deal.name,
        }).insert(ignore_permissions=True)
        
         # Now mark the deal as Won (after locations are linked)
        deal.status = "Won"
        deal.save(ignore_permissions=True)

        # Verify both created projects have the master customer
        projects = frappe.db.get_list(
            "Project",
            filters={"customer": primary_customer.name, "project_type": "Deployment"},
            fields=["name", "custom_master_customer"]
        )
        self.assertEqual(len(projects), 2)
        for project in projects:
            self.assertEqual(project["custom_master_customer"], master_customer.name)
