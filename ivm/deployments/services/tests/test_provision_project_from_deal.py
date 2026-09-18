"""Integration tests for ivm.deployments.services.provision_project_from_deal"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite

from ivm.deployments.services.provision_project_from_deal import create_projects_from_deal


def _make_deal(organization=None, custom_customer=None, custom_master_customer=None, contacts=None):
	"""Helper to create a CRM Deal for testing"""
	if not frappe.db.exists("CRM Deal Status", "Qualification"):
		frappe.get_doc({"doctype": "CRM Deal Status", "status": "Qualification"}).insert(
			ignore_permissions=True,
		)
	return frappe.get_doc({
		"doctype": "CRM Deal",
		"status": "Qualification",
		"organization": organization,
		"custom_customer": custom_customer,
		"custom_master_customer": custom_master_customer,
		"contacts": contacts or [],
		"custom_hubspot_deal_name": f"Test Deal {frappe.generate_hash(length=8)}",
	}).insert(ignore_permissions=True)


def _make_location(deal_name, hubspot_site_id=None, wrap_type=None, locale=None, smartstation_details=None):
	"""Helper to create a Deployment Location for testing"""
	doc = frappe.get_doc({
		"doctype": "Deployment Location",
		"location_name": f"Test Location {frappe.generate_hash(length=8)}",
		"crm_deal": deal_name,
		"hubspot_site_id": hubspot_site_id,
		"wrap_type": wrap_type,
		"locale": locale,
		"smartstation_details": smartstation_details or [],
	})
	doc.insert(ignore_permissions=True)
	return doc


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


class TestFlatFieldMapping(ERPNextTestSuite):
	"""_copy_flat_fields via create_projects_from_deal: DEAL_TO_PROJECT_FIELDS / LOCATION_TO_PROJECT_FIELDS"""

	def test_deal_fields_copied_onto_project(self):
		deal = _make_deal()
		frappe.db.set_value("CRM Deal", deal.name, "custom_opportunity_term", "36 months")
		frappe.db.set_value("CRM Deal", deal.name, "deal_owner", "Administrator")
		location = _make_location(deal.name, wrap_type="IVM Wrap", locale="Domestic")

		created = create_projects_from_deal(deal.name)
		self.assertEqual(len(created), 1)
		project = frappe.get_doc("Project", created[0])
		self.assertEqual(project.opportunity_term, "36 months")
		self.assertEqual(project.sales_rep, "Administrator")
		self.assertEqual(project.wrap_type, "IVM Wrap")
		self.assertEqual(project.locale, "Domestic")

	def test_empty_source_fields_not_copied(self):
		deal = _make_deal()
		location = _make_location(deal.name)

		created = create_projects_from_deal(deal.name)
		project = frappe.get_doc("Project", created[0])
		self.assertFalse(project.wrap_type)


class TestChildTableCopying(ERPNextTestSuite):
	"""_copy_child_tables via create_projects_from_deal"""

	def test_smartstation_rows_copied_to_project_child_table(self):
		deal = _make_deal()
		location = _make_location(
			deal.name,
			smartstation_details=[{"machine_name": "M1", "equipment_type": "New"}],
		)

		created = create_projects_from_deal(deal.name)
		project = frappe.get_doc("Project", created[0])
		self.assertEqual(len(project.custom_deployment_smartstation_details), 1)
		self.assertEqual(project.custom_deployment_smartstation_details[0].machine_name, "M1")

	def test_no_rows_means_no_child_table_entries(self):
		deal = _make_deal()
		location = _make_location(deal.name)

		created = create_projects_from_deal(deal.name)
		project = frappe.get_doc("Project", created[0])
		self.assertEqual(len(project.custom_deployment_smartstation_details), 0)


class TestPrimaryContactAndCustomerCopying(ERPNextTestSuite):
	"""primary contact resolution + customer/icorp_client_id copying in create_projects_from_deal"""

	def test_primary_contact_copied_to_project(self):
		contact = frappe.get_doc({"doctype": "Contact", "first_name": f"PC {frappe.generate_hash(length=6)}"})
		contact.insert(ignore_permissions=True)
		deal = _make_deal(contacts=[{"contact": contact.name, "is_primary": 1}])
		location = _make_location(deal.name)

		created = create_projects_from_deal(deal.name)
		project = frappe.get_doc("Project", created[0])
		self.assertEqual(project.contact_name, contact.name)

	def test_customer_and_icorp_client_id_copied(self):
		customer = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": frappe.generate_hash(length=10),
			"customer_group": "_Test Customer Group",
			"territory": "_Test Territory",
			"icorp_client_id": "ICORP-999",
		})
		customer.insert(ignore_permissions=True)
		deal = _make_deal()
		frappe.db.set_value("CRM Deal", deal.name, "custom_customer", customer.name)
		location = _make_location(deal.name)

		created = create_projects_from_deal(deal.name)
		project = frappe.get_doc("Project", created[0])
		self.assertEqual(project.customer, customer.name)
		self.assertEqual(project.client_id, "ICORP-999")


class TestDuplicateSkipByHubspotSiteId(ERPNextTestSuite):
	"""dup-skip logic keyed on Deployment Location.hubspot_site_id"""

	def test_second_call_skips_existing_project_for_same_site_id(self):
		deal = _make_deal()
		location = _make_location(deal.name, hubspot_site_id="SITE-DUP-001")

		first = create_projects_from_deal(deal.name)
		self.assertEqual(len(first), 1)

		second = create_projects_from_deal(deal.name)
		self.assertEqual(len(second), 0)

	def test_no_hubspot_site_id_second_call_hits_duplicate_name(self):
		# The dup-skip check in _create_project_for_location is keyed
		# entirely on hubspot_site_id. Without one, project_name is
		# deterministic from site_name + deal name with nothing else to
		# differentiate a second call, so it collides on Project's unique
		# project_name constraint instead of skipping gracefully -- this
		# documents that current, real limitation rather than a clean skip.
		deal = _make_deal()
		location = _make_location(deal.name)

		first = create_projects_from_deal(deal.name)
		self.assertEqual(len(first), 1)

		with self.assertRaises(frappe.UniqueValidationError):
			create_projects_from_deal(deal.name)
