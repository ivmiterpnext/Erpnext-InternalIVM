"""Integration tests for ivm.deals.doctype.deployment_location.deployment_location"""

import frappe
from erpnext.tests.utils import ERPNextTestSuite


def _ensure_deal_status(status):
    if not frappe.db.exists("CRM Deal Status", status):
        frappe.get_doc({"doctype": "CRM Deal Status", "status": status}).insert(
            ignore_permissions=True,
        )


def _make_deal():
    _ensure_deal_status("Qualification")
    return frappe.get_doc({
        "doctype": "CRM Deal",
        "status": "Qualification",
        "custom_hubspot_deal_name": f"Test Deal {frappe.generate_hash(length=8)}",
    }).insert(ignore_permissions=True)


def _make_location(deal_name=None, **table_rows):
    """Create a Deployment Location. table_rows maps child-table fieldname
    (e.g. smartstation_details) to a list of row dicts."""
    if deal_name is None:
        deal_name = _make_deal().name
    data = {
        "doctype": "Deployment Location",
        "location_name": f"Loc {frappe.generate_hash(length=8)}",
        "crm_deal": deal_name,
    }
    data.update(table_rows)
    doc = frappe.get_doc(data)
    doc.insert(ignore_permissions=True)
    return doc


class TestSanitiseChildSelectFields(ERPNextTestSuite):
    """validate: _sanitise_child_select_fields"""

    def test_valid_value_untouched(self):
        doc = _make_location(smartstation_details=[{"machine_name": "M1", "equipment_type": "New"}])
        self.assertEqual(doc.smartstation_details[0].equipment_type, "New")

    def test_boolean_ish_value_normalized(self):
        doc = _make_location(smartstation_details=[{"machine_name": "M1", "casters": "yes"}])
        self.assertEqual(doc.smartstation_details[0].casters, "Yes")

    def test_invalid_value_cleared(self):
        doc = _make_location(smartstation_details=[{"machine_name": "M1", "equipment_type": "Bogus"}])
        self.assertEqual(doc.smartstation_details[0].equipment_type, "")

    def test_empty_value_left_alone(self):
        doc = _make_location(smartstation_details=[{"machine_name": "M1", "equipment_type": ""}])
        self.assertEqual(doc.smartstation_details[0].equipment_type, "")

    def test_all_tables_sanitised_independently(self):
        doc = _make_location(
            smartstation_details=[{"machine_name": "M1", "equipment_type": "Bogus"}],
            smartlocker_details=[{"machine_name": "M2", "equipment_type": "AlsoBogus"}],
        )
        self.assertEqual(doc.smartstation_details[0].equipment_type, "")
        self.assertEqual(doc.smartlocker_details[0].equipment_type, "")


class TestUpdateDeviceQuantities(ERPNextTestSuite):
    """validate: _update_device_quantities"""

    def test_quantity_matches_row_count_all_tables(self):
        doc = _make_location(
            smartstation_details=[{"machine_name": "M1"}, {"machine_name": "M2"}, {"machine_name": "M3"}],
            smartvault_details=[{"machine_name": "V1"}],
        )
        self.assertEqual(doc.number_of_machines, 3)
        self.assertEqual(doc.number_of_vaults, 1)
        self.assertEqual(doc.number_of_primary_lockers, 0)
        self.assertEqual(doc.number_of_secondary_lockers, 0)
        self.assertEqual(doc.number_of_kiosks, 0)

    def test_recalculated_after_row_removed(self):
        doc = _make_location(smartstation_details=[{"machine_name": "M1"}, {"machine_name": "M2"}])
        self.assertEqual(doc.number_of_machines, 2)
        doc.set("smartstation_details", doc.smartstation_details[:1])
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.number_of_machines, 1)

    def test_recalculated_after_row_added_on_resave(self):
        doc = _make_location(smartstation_details=[{"machine_name": "M1"}])
        self.assertEqual(doc.number_of_machines, 1)
        doc.append("smartstation_details", {"machine_name": "M2"})
        doc.save(ignore_permissions=True)
        self.assertEqual(doc.number_of_machines, 2)


class TestValidateUniqueMachineNames(ERPNextTestSuite):
    """validate: _validate_unique_machine_names"""

    def test_duplicate_within_same_table_throws(self):
        with self.assertRaises(frappe.ValidationError) as ctx:
            _make_location(smartstation_details=[
                {"machine_name": "DUP"}, {"machine_name": "DUP"},
            ])
        self.assertIn("Duplicate machine name", str(ctx.exception))
        self.assertIn("DUP", str(ctx.exception))

    def test_duplicate_across_different_tables_allowed(self):
        doc = _make_location(
            smartstation_details=[{"machine_name": "SHARED"}],
            smartlocker_details=[{"machine_name": "SHARED"}],
        )
        self.assertEqual(doc.smartstation_details[0].machine_name, "SHARED")
        self.assertEqual(doc.smartlocker_details[0].machine_name, "SHARED")

    def test_distinct_names_pass(self):
        doc = _make_location(smartstation_details=[
            {"machine_name": "A1"}, {"machine_name": "A2"},
        ])
        self.assertEqual(len(doc.smartstation_details), 2)

    def test_blank_names_ignored(self):
        # machine_name is reqd=1 at the schema level, so a real insert() would
        # block on MandatoryError before validate()'s own duplicate-check logic
        # ever runs. Bypass that gate here specifically to exercise the
        # `if not name: continue` skip branch in _validate_unique_machine_names.
        doc = frappe.get_doc({
            "doctype": "Deployment Location",
            "location_name": f"Loc {frappe.generate_hash(length=8)}",
            "crm_deal": _make_deal().name,
            "smartstation_details": [{"machine_name": ""}, {"machine_name": None}],
        })
        doc.flags.ignore_mandatory = True
        doc.insert(ignore_permissions=True)
        self.assertEqual(len(doc.smartstation_details), 2)


class TestValidateIntegration(ERPNextTestSuite):
    """validate: all three sub-hooks applied together"""

    def test_all_three_hooks_apply_together(self):
        doc = _make_location(
            smartstation_details=[
                {"machine_name": "M1", "equipment_type": "Bogus"},
                {"machine_name": "M2", "equipment_type": "New"},
            ],
        )
        self.assertEqual(doc.smartstation_details[0].equipment_type, "")
        self.assertEqual(doc.smartstation_details[1].equipment_type, "New")
        self.assertEqual(doc.number_of_machines, 2)
