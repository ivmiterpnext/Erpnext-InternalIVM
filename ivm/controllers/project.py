import frappe
from frappe import _
from frappe.utils import getdate, add_days
from erpnext.projects.doctype.project.project import Project as OriginalProjectController
import math


class CustomProjectController(OriginalProjectController):
    def validate(self):
        OriginalProjectController.validate(self)
        self.update_provide_planogram_due_date()
        self.update_approve_planogram_and_locker_config_due()
        self.update_pog_created_in_database_due()
        self.update_sample_products_due()
    def update_sample_products_due(self):
        if not self.placement_agreement:
            return
        base_days = 2 if (self.expedited_delivery) else (7 if self.locale and self.locale == "Domestic" else 13)
        added_days = int(self.added_days) if self.added_days else 0
        due_date = get_sample_products_due_date(self.placement_agreement, base_days, added_days)
        self.sample_products_due = due_date
        self.sample_badge_due = due_date

    def update_provide_planogram_due_date(self):
        if not self.placement_agreement:
            return

        base_days = 7 if (self.expedited_delivery) else (17 if self.locale and self.locale == "Domestic" else 23)
        added_days = int(self.added_days) if self.added_days else 0
        self.provide_planogram_due = get_provide_planogram_base_date(self.placement_agreement, base_days, added_days)

    def update_approve_planogram_and_locker_config_due(self):
        if not self.placement_agreement:
            return

        base_days = 11 if (self.expedited_delivery) else (25 if self.locale and self.locale == "Domestic" else 31)
        added_days = int(self.added_days) if self.added_days else 0
        self.approve_planogram_and_locker_config_due = get_provide_planogram_base_date(self.placement_agreement, base_days, added_days)

    def update_pog_created_in_database_due(self):
        if not self.placement_agreement:
            return

        base_days = 10 if (self.expedited_delivery) else (24 if self.locale and self.locale == "Domestic" else 27)
        added_days = int(self.added_days) if self.added_days else 0
        self.pog_created_in_database_due = get_provide_planogram_base_date(self.placement_agreement, base_days, added_days)


# preparing date based on the placement agreement, base date and added days data #
def get_provide_planogram_base_date(date, base_days, added_days):
    try:
        no_of_days = base_days + get_no_days(date, base_days, added_days)
        return add_days(date, no_of_days)
    except Exception as e:
        frappe.msgprint(e)

def get_no_days(date, base_days, added_days):
    weekday = getdate(date).weekday()

    if (weekday == 5):
        return int(math.ceil(((base_days + added_days)/5)*2))
    elif (weekday == 6):
        return (- base_days - added_days + base_days + int(math.ceil(((base_days + added_days)/5)*2)))
    else:
        days_maps = {0: -1, 1: 0, 2: 1, 3: 2, 4:3}
        return int((math.floor(base_days + added_days + days_maps.get(weekday))/5)*2)

def get_sample_products_due_date(placement_agreement, base_days, added_days):
    weekday = getdate(placement_agreement).weekday()
    if weekday == 5:
        return add_days(placement_agreement, base_days + added_days + math.ceil(((base_days + added_days) / 5) * 2))
    elif weekday == 6:
        return add_days(placement_agreement, - base_days - added_days -0 + base_days + math.ceil(((base_days + added_days) / 5) * 2))
    else:
        return add_days(placement_agreement, base_days + added_days + int(math.floor((base_days + added_days + {0: -1, 1: 0, 2: 1, 3: 2, 4: 3}.get(weekday, 0)) / 5) * 2))
    
############################# end of calculations ################################
