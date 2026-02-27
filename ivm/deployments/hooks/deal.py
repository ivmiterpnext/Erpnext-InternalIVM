# This file will go in whatever module deal lives in

from ivm.deployments.services.provision_deployment import generate_deployment, is_won_deal_status

def on_update(deal, method=None):
    if is_won_deal_status(deal.status):
        generate_deployment(deal)