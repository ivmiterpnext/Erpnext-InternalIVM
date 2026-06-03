"""
Date calculation utilities for deployment milestone scheduling.
"""

import math
import frappe
from frappe.utils import add_days, getdate


def get_provide_planogram_base_date(
    date: str, base_days: int, added_days: int
) -> str | None:
    """Return a due date offset from *date* by *base_days* + *added_days*, adjusted for weekends."""

    try:
        total_offset = base_days + added_days + _get_weekend_offset(date, base_days, added_days)
        return add_days(date, total_offset)

    except Exception:
        frappe.log_error(
            title="Due-date calculation failed",
            message=frappe.get_traceback(with_context=True),
        )

        return None

def _get_weekend_offset(date: str, base_days: int, added_days: int) -> int:
    """Calculate extra days needed to skip weekends for a given start weekday."""

    weekday = getdate(date).weekday()
    total = base_days + added_days

    if weekday == 6:  # Sunday
        return int(math.ceil((total / 5) * 2))
    if weekday == 5:  # Saturday
        return (-added_days - 1) + int(math.ceil((total / 5)) * 2)

    # Monday–Friday
    weekday_offset = {0: -1, 1: 0, 2: 1, 3: 2, 4: 3}
    return int(math.floor((total + weekday_offset[weekday]) / 5) * 2)

def calculate_days(added_days: int, weekday: int, base_days: int) -> int:
    """Return total calendar days (including weekend padding) for a weekday-aware offset."""

    total = base_days + added_days

    if weekday == 4:  # Friday
        return total + int(math.ceil((total / 5) * 2))
    if weekday == 5:  # Saturday
        return total - 1 + int(math.ceil((total / 5) * 2))
    if weekday == 6:  # Sunday
        return total + int(math.floor(((total - 1) / 5) * 2))

    # Monday–Thursday
    return total + int(math.floor(((total + weekday) / 5) * 2))

def user_and_restriction_requirements_due(
    placement_agreement: str, added_days: int | str, expedited_delivery: bool
) -> str:
    """Compute the user & restriction requirements due date."""

    weekday = getdate(placement_agreement).weekday()
    base_days = 14 if expedited_delivery else 20
    return add_days(placement_agreement, calculate_days(int(added_days), weekday, base_days))
