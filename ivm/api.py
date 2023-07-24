import frappe
import requests

# Function to get the SalesLoft API token from the "SalesLoft Settings" doctype
def get_salesloft_api_token():
    api_token = frappe.get_value("SalesLoft Settings", None, "salesloft_api_token")

    if not api_token:
        frappe.throw("SalesLoft API Token not set in SalesLoft Settings")

    return api_token

# Function to make API calls to SalesLoft
def make_salesloft_api_call(url, method="GET", payload=None):
    SALESLOFT_API_TOKEN = get_salesloft_api_token()

    if not SALESLOFT_API_TOKEN:
        frappe.throw("SalesLoft API Token not set in SalesLoft Settings")

    headers = {"Authorization": f"Bearer {SALESLOFT_API_TOKEN}"}
    response = requests.request(method, url, json=payload, headers=headers)

    return response

# Function to check if the SalesLoft user already exists
@frappe.whitelist(allow_guest=True)
def check_salesloft_user(email):
    url = "https://api.salesloft.com/v2/people"
    response = make_salesloft_api_call(url)

    for person in response.json().get("data", []):
        if person.get("email_address") == email:
            return person

    return None

# Function to create a new SalesLoft person
@frappe.whitelist(allow_guest=True)
def create_salesloft_person(email, name):
    url = "https://api.salesloft.com/v2/people"
    payload = {
        "email_address": email,
        "first_name": name,
        # Add any additional fields as per your requirements
    }

    response = make_salesloft_api_call(url, method="POST", payload=payload)

    if response.status_code == 201:
        created_person = response.json()
        return created_person["data"]["id"]
    else:
        return None
 