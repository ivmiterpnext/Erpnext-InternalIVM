# This file will go in whatever module deal lives in

from ivm.deployments.services.provision_deployment import generate_deployment, is_won_deal_status

def on_update(deal, method=None):
    if is_won_deal_status(deal.status):
        location_id = check_if_location_exists(deal.location_name, deal.client_id)

        if location_id is None or location_id == 0:
            create_location(deal.location_name, deal.client_id)

        generate_deployment(deal)
