import math
import frappe
from frappe.utils import getdate, add_days


def get_provide_planogram_base_date(date, base_days, added_days):
	try:
		no_of_days = base_days + added_days + _get_weekend_offset(date, base_days, added_days)
		return add_days(date, no_of_days)
	except Exception as e:
		frappe.msgprint(e)


def _get_weekend_offset(date, base_days, added_days):
	weekday = getdate(date).weekday()
	if weekday == 6:
		return int(math.ceil(((base_days + added_days) / 5) * 2))
	elif weekday == 5:
		return (-base_days - added_days - 1 + base_days) + (int(math.ceil(((base_days + added_days) / 5)) * 2))
	else:
		days_map = {0: -1, 1: 0, 2: 1, 3: 2, 4: 3}
		return int((math.floor(base_days + added_days + days_map.get(weekday)) / 5) * 2)


def calculate_days(added_days, weekday, base_days):
	total = base_days + added_days
	if weekday == 4:
		return total + int(math.ceil((total / 5) * 2))
	elif weekday == 5:
		return total - 1 + int(math.ceil((total / 5) * 2))
	elif weekday == 6:
		return total + int(math.floor(((total - 1) / 5) * 2))
	else:
		return total + int(math.floor(((total + weekday) / 5) * 2))


def user_and_restriction_requirements_due(placement_agreement, added_days, expedited_delivery):
	weekday = getdate(placement_agreement).weekday()
	base_days = 14 if expedited_delivery else 20
	return add_days(placement_agreement, calculate_days(int(added_days), weekday, base_days))
