# This file will go in whatever module deal lives in

from ivm.deployments.services.provision_deployment import ensure_project_for_closed_opportunity

def on_update(doc, method=None):
    ensure_project_for_closed_opportunity(doc)