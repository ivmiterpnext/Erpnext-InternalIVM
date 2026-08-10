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


def get_secret(name):
    """Retrieve a single secret value from Azure Key Vault by name."""
    return get_secret_client().get_secret(name).value


def get_secrets(names):
    """Retrieve multiple secret values from Azure Key Vault in one client session."""
    client = get_secret_client()
    return {name: client.get_secret(name).value for name in names}
