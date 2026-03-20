# This file will go in whatever module deal lives in

from ivm.deployments.services.create_machines_from_project import create_machines_from_project

def after_insert(doc, method=None):
    create_machines_from_project(doc)
