import frappe
from bs4 import BeautifulSoup
import requests
import json
from datetime import datetime

@frappe.whitelist(allow_guest=True)
def task_creation():
    data = frappe.request.get_json()
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    user_id = salesloft_doc.user_id
    created_by_user = data["created_by_user"]["id"]
    if created_by_user == user_id:
        description = data["description"]
        person_id = data["person"]["id"]
        task_id = data["id"]
        date_string = data["due_date"]
        subject = data["subject"]
        date_object = datetime.strptime(date_string, '%Y-%m-%d').date()
        person_email_id = get_person_id_or_email(personid=person_id)
        if person_email_id:
            person_email_id = person_email_id.strip()
            doc = frappe.new_doc("ToDo")
            doc.reference_type = "Lead"
            q = '''select name from tabLead where email_id = %s;'''
            res = frappe.db.sql(q,person_email_id,as_list=True)
            reference_name = res[0][0]
            if description == None:
                description = "None"
            doc.description = f'subject : {subject}<br/> description : {description}'
            doc.date = date_object
            doc.reference_type = "Lead"
            doc.reference_name = reference_name
            doc.task_id = task_id
            doc.insert(ignore_permissions=True)



@frappe.whitelist(allow_guest=True)
def task_updation():
    data = frappe.request.get_json()
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    user_id = salesloft_doc.user_id
    created_by_user = data["created_by_user"]["id"]
    if created_by_user == user_id:
        description = data["description"]
        person_id = data["person"]["id"]
        task_id = data["id"]
        date_string = data["due_date"]
        subject = data["subject"]
        date_object = datetime.strptime(date_string, '%Y-%m-%d').date()
        q = '''select name from tabToDo where task_id = %s;'''
        res = frappe.db.sql(q,task_id,as_list=True)
        if not res:
            person_email_id = get_person_id_or_email(personid=person_id)
            if person_email_id:
                person_email_id = person_email_id.strip()
                doc = frappe.new_doc("ToDo")
                doc.reference_type = "Lead"
                q = '''select name from tabLead where email_id = %s;'''
                res = frappe.db.sql(q,person_email_id,as_list=True)
                reference_name = res[0][0]
                if description == None:
                    description = "None"
                doc.description = f'subject : {subject}<br/> description : {description}'
                doc.date = date_object
                doc.reference_type = "Lead"
                doc.reference_name = reference_name
                doc.task_id = task_id
                doc.insert(ignore_permissions=True)
                
        else:
            name = res[0][0]
            doc = frappe.get_doc("ToDo",name)
            if description == None:
                description = "None"
            doc.description = f'subject : {subject}<br/> description : {description}'
            doc.date = date_object
            doc.save(ignore_permissions=True)
        


@frappe.whitelist(allow_guest=True)
def note_creation():
    data = frappe.request.get_json()
    person_id= data["associated_with"]["id"]
    if person_id:
        note = data["content"]
        person_email_id = get_person_id_or_email(personid=person_id)
        q = '''select name from tabLead where email_id = %s;'''
        res = frappe.db.sql(q,person_email_id,as_list=True)
        name = res[0][0]
        if name:
            doc = frappe.get_doc("Lead",name)
            doc.append("notes",{
            "note":note,
            "added_by":frappe.session.user,
            "added_on":datetime.now(),
            "id":data["id"]
            })
            doc.save(ignore_permissions=True)


@frappe.whitelist(allow_guest=True)
def note_updation():
    data = frappe.request.get_json()
    person_id= data["associated_with"]["id"]
    if person_id:
        note = data["content"]
        person_email_id = get_person_id_or_email(personid=person_id)
        q = '''select name from tabLead where email_id = %s;'''
        res = frappe.db.sql(q,person_email_id,as_list=True)
        name = res[0][0]
        if name:
            doc = frappe.get_doc('Lead', name)
            for child in doc.get('notes'):
                if int(child.get('id')) == data["id"]:
                    child.note = note
                    child.added_by = frappe.session.user
                    child.added_on = datetime.now()
                    break
            else:
                doc.append("notes",{
                "note":note,
                "added_by":frappe.session.user,
                "added_on":datetime.now(),
                "id":data["id"]
                })
            doc.save(ignore_permissions=True)
    

def list_webhooks():
    ids_of_webhooks=[]
    callback_url=""
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token
    url = "https://api.salesloft.com/v2/webhook_subscriptions"

    payload={}
    headers = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {access_token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)
    response = response.json()
    data = response["data"]
    for i in data:
        ids_of_webhooks.append(i["id"])
    
    if ids_of_webhooks:
        callback_url = data[0]["callback_url"]
    return ids_of_webhooks,callback_url

        
def set_guid():
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token
    email = salesloft_doc.salesloft_user_email
    if email:
        url = "https://api.salesloft.com/v2/users"
        payload={}
        headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
        }

        response = requests.request("GET", url, headers=headers, data=payload)
        response = response.json()
        data = response["data"]
        for i in data:
            if i['email'].strip()==email.strip():
                salesloft_doc.user_id = i["id"]
                salesloft_doc.guid = i["guid"]
                salesloft_doc.save(ignore_permissions=True)
                break


def get_person_id_or_email(firstname="",personid=0):
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token
    guid = salesloft_doc.guid
    url = "https://api.salesloft.com/v2/people"

    payload={"owned_by_guid":[guid]}
    if personid !=0:
        payload = {"owned_by_guid":[guid],"ids":[personid]}
    headers = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {access_token}'
    }

    response = requests.request("GET", url, headers=headers, data=payload)

    response = response.json()
    data = response["data"]
    if firstname !="":
        for i in data:
            if i['first_name']==firstname:
                return i["id"]
    
    if personid !=0:
        for i in data:
            if i['id']==personid:
                email = i["email_address"]
                email = email.strip()
                return  email
    
    else:
        return
 


@frappe.whitelist(allow_guest=True)
def create_webhooks():
    event_types = {"note_created": "note_creation","note_updated":"note_updation","task_created":"task_creation","task_updated":"task_updation"}
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token
    site_url = salesloft_doc.your_site_url
    ids_of_webhooks,callback_url=list_webhooks()
    if callback_url !="":
        index_of_app= callback_url.index("api")
        callback_url=callback_url[0:index_of_app-1]
    if site_url[-1]=="/":
        site_url = site_url[:-1]
    
    if not ids_of_webhooks:
        for i in event_types:
            url = "https://api.salesloft.com/v2/webhook_subscriptions"

            payload = {"event_type": i,"callback_url":f'{site_url}/api/method/ivm.salesloft_activity.{event_types[i]}',"callback_token":event_types[i]}
            headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
            }

            response = requests.request("POST", url, headers=headers, data=payload)

        set_guid()
    
    elif callback_url != site_url:
        delete_webhooks()
        for i in event_types:
            url = "https://api.salesloft.com/v2/webhook_subscriptions"

            payload = {"event_type": i,"callback_url":f'{site_url}/api/method/ivm.salesloft_activity.{event_types[i]}',"callback_token":event_types[i]}
            headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
            }

            response = requests.request("POST", url, headers=headers, data=payload)

        set_guid()
 

@frappe.whitelist(allow_guest=True)
def delete_webhooks():
    salesloft_doc = frappe.get_doc("SalesLoft Settings")
    access_token = salesloft_doc.salesloft_api_token
    site_url = salesloft_doc.your_site_url
    if site_url[-1]=="/":
        site_url = site_url[:-1]
    ids_of_webhooks,callback_url=list_webhooks()
    def delete(id):
        url = f"https://api.salesloft.com/v2/webhook_subscriptions/{id}"

        payload={}
        headers = {
        'Authorization': f'Bearer {access_token}'
        }

        response = requests.request("DELETE", url, headers=headers, data=payload)
        
    if ids_of_webhooks and (site_url == callback_url):
        for i in ids_of_webhooks:
            delete(i)


