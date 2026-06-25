"""Azure Key Vault client and generic config helpers."""

import os

import frappe
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


def get_config_value(key, default=None):
    return frappe.conf.get(key.lower()) or os.environ.get(key.upper()) or default

def get_secret_client():
    vault_url = get_config_value("AZURE_KEYVAULT_URL")
    if not vault_url:
        frappe.throw("azure_keyvault_url is not set in site config or environment variables.")

    return SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
