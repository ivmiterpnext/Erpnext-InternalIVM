import frappe


@frappe.whitelist()
def get_deployment_locations(deal_name):
    return frappe.get_all(
        "Deployment Location",
        filters={"crm_deal": deal_name},
        fields=[
            "name",
            "location_name",
            "locale",
            "number_of_machines",
            "number_of_primary_lockers",
            "number_of_secondary_lockers",
            "number_of_vaults",
            "number_of_kiosks",
        ],
        order_by="creation asc",
    )
