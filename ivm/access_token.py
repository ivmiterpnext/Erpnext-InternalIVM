import frappe
import requests
import json
import datetime
from bs4 import BeautifulSoup


def generate_access_token():
    doc = frappe.get_doc("Office 365 Settings")
    client_id = doc.client_id
    client_secret = doc.client_secret
    scope = "https://graph.microsoft.com/.default"
    tenet_id = doc.tenet_id
    token_url = f'https://login.microsoftonline.com/{tenet_id}/oauth2/v2.0/token'

    # Step 1: Obtain an access token
    token_data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope
    }

    response = requests.post(token_url, data=token_data)
    token_json = response.json()
    access_token = token_json.get("access_token", response)

    if not access_token:
        raise Exception("Access token not obtained")

    return access_token


@frappe.whitelist()
def get_events(_retried=False):
    doc = frappe.get_doc("Office 365 Settings")
    access_token = doc.access_token
    user_id = doc.user_id

    if doc.enable == 1:
        headers = {
            'Authorization': f'Bearer {access_token}'
        }

        # Replace 'default' with the specific calendar ID if needed
        calendar_id = 'default'
        api_url = f'https://graph.microsoft.com/v1.0/users/{user_id}/events'
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:

            existed_ids_in_frappe = frappe.db.get_list(
                "Calendar Events", pluck='id')
            events_ids_in_cal = []
            events = response.json()['value']
            for event in events:
                events_ids_in_cal.append(event['id'])
                if event["id"] not in existed_ids_in_frappe:

                    content = event["body"]['content']
                    soup = BeautifulSoup(content, 'html.parser')
                    meeting_link_tag = soup.find(
                        'a', class_='me-email-headline')
                    link = ""
                    if meeting_link_tag:
                        # Extract the href attribute (link)from the <a> tag
                        meeting_link = meeting_link_tag.get('href')
                        link = meeting_link
                    else:
                        print("Teams meeting link not found in the HTML.")

                    def date(datetime_string):
                        parsed_datetime = datetime.datetime.strptime(
                            datetime_string, '%Y-%m-%dT%H:%M:%S.%f0')
                        return parsed_datetime.date(), parsed_datetime.time()

                    start, stime = date(event["start"]["dateTime"])
                    end, etime = date(event["end"]["dateTime"])
                    zone = event["start"]["timeZone"]
                    time = str(stime) + " to " + str(etime) + "  " + zone
                    attendees = ""

                    for i in event["attendees"]:
                        attendees = attendees+" "+i["emailAddress"]["address"]

                    doc = frappe.new_doc("Calendar Events")

                    doc.link = link
                    doc.event_name = event["subject"]
                    doc.start_date = start
                    doc.end_date = end
                    doc.organiser = event["organizer"]['emailAddress']['name']
                    doc.email = event["organizer"]['emailAddress']['address']
                    doc.attendees = attendees
                    doc.time = time
                    doc.description = event['bodyPreview']
                    doc.id = event["id"]
                    doc.insert()
                    doc.save()

                else:
                    CE = frappe.db.get_list("Calendar Events", filters={
                                            "id": event["id"]}, fields=["name"])
                    doc = frappe.get_doc("Calendar Events", CE[0]['name'])

                    def date(datetime_string):
                        parsed_datetime = datetime.datetime.strptime(
                            datetime_string, '%Y-%m-%dT%H:%M:%S.%f0')
                        return parsed_datetime.date(), parsed_datetime.time()

                    content = event["body"]['content']
                    soup = BeautifulSoup(content, 'html.parser')
                    meeting_link_tag = soup.find(
                        'a', class_='me-email-headline')
                    link = ""
                    if meeting_link_tag:
                        # Extract the href attribute (link)from the <a> tag
                        meeting_link = meeting_link_tag.get('href')
                        link = meeting_link
                    attendees = ""
                    start, stime = date(event["start"]["dateTime"])
                    end, etime = date(event["end"]["dateTime"])
                    zone = event["start"]["timeZone"]
                    time = str(stime) + " to " + str(etime) + "  " + zone

                    for i in event["attendees"]:
                        attendees = attendees+" "+i["emailAddress"]["address"]
                    change = False
                    if doc.event_name != event["subject"]:
                        doc.event_name = event["subject"]
                        change = True
                    if doc.start_date != start:
                        doc.start_date = start
                        change = True
                    if doc.end_date != end:
                        doc.end_date = end
                        change = True
                    if doc.organiser != event["organizer"]['emailAddress']['name']:
                        doc.organiser = event["organizer"]['emailAddress']['name']
                        change = True
                    if doc.email != event["organizer"]['emailAddress']['address']:
                        doc.email = event["organizer"]['emailAddress']['address']
                        change = True
                    if doc.attendees != attendees:
                        doc.attendees = attendees
                        change = True
                    if doc.description != event['bodyPreview']:
                        doc.description = event['bodyPreview']
                        change = True
                    if doc.link != link:
                        doc.link = link
                        change = True
                    if doc.time != time:
                        doc.time = time
                        change = True

                    if change:
                        doc.save()

                    if doc.name != event['subject']:
                        q = '''update `tabCalendar Events` set name = %s,event_name = %s where name = %s'''
                        args = (event["subject"],
                                event["subject"], CE[0]['name'])
                        frappe.db.sql(q, args)

            for i in existed_ids_in_frappe:
                if i not in events_ids_in_cal:
                    q = '''delete from `tabCalendar Events` where id = %s;'''
                    frappe.db.sql(q, i)

            return
        else:
            if _retried:
                frappe.log_error(
                    title="Office 365 get_events: retry failed",
                    message=f"Graph API call failed again after token refresh. Status: {response.status_code}, Body: {response.text[:500]}",
                )
                return response.json(), access_token
            access = generate_access_token()
            doc = frappe.get_doc("Office 365 Settings")
            doc.access_token = access
            doc.save()
            return get_events(_retried=True)
    else:
        return "Functionality not enabled in the Office 365 Settings", frappe.msgprint("Functionality not enabled in the Office 365 Settings")
