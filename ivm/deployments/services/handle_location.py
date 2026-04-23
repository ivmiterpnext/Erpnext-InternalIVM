import frappe
from ivm.ivm.utils.api_utils import icorp_api_get

# def check_if_location_exists(location_name, client_id):
#     # tbl_SV_Location has client id and and location name, most recent format is:
#     # client_name - city, state
#     # country is used in place of state if international
#         # 1682	OpenAI - 1515 San Francisco, CA
#         # 1682	OpenAI - 1455 San Francisco, CA
#         # What are these numbers and what do we do in this isntance?

# def create_location(location_name, client_id):
#     # Placeholder for location creation logic
#     # You might use icorp_api_post here in real implementation
#     frappe.msgprint(f"Creating location: {location_name} for client {client_id}")
#     # Return a dummy id for now
#     return 1
