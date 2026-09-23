"""
Date calculation utilities for deployment milestone scheduling.
"""

from frappe.utils import add_days, getdate


def add_business_days(start_date, business_days: int):
	"""Shift start_date by business_days weekdays. Negative values go backward;
	result always lands on Mon-Fri.
	"""
	date = getdate(start_date)
	remaining = abs(int(business_days))
	step = 1 if business_days >= 0 else -1
	while remaining > 0:
		date = add_days(date, step)
		if date.weekday() < 5:
			remaining -= 1
	return date
