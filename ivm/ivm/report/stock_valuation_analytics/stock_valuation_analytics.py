# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
import datetime

import frappe
from frappe import _, scrub
from frappe.utils import get_datetime, get_first_day_of_week, get_quarter_start, getdate
from frappe.utils import get_first_day as get_first_day_of_month

from erpnext.accounts.utils import get_fiscal_year
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.utils import is_reposting_item_valuation_in_progress


def execute(filters=None):
	is_reposting_item_valuation_in_progress()
	filters = frappe._dict(filters or {})
	period_columns = get_period_columns(filters)
	columns = get_columns(period_columns)
	data = get_data(filters)

	return columns, data


def get_period_columns(filters):
	period_columns = []
	ranges = get_period_date_ranges(filters)

	for _dummy, end_date in ranges:
		period = get_period(end_date, filters)
		period_key = scrub(period)

		period_columns.append(
			{
				"label": _("{0} Qty").format(period),
				"fieldname": f"{period_key}_qty",
				"fieldtype": "Float",
				"width": 90,
			}
		)
		period_columns.append(
			{
				"label": _("{0} Price").format(period),
				"fieldname": f"{period_key}_price",
				"fieldtype": "Currency",
				"width": 100,
			}
		)
		period_columns.append(
			{
				"label": _("{0} Total").format(period),
				"fieldname": f"{period_key}_total",
				"fieldtype": "Currency",
				"width": 110,
			}
		)

	return period_columns


def get_columns(period_columns):
	columns = [
		{"label": _("Item"), "options": "Item", "fieldname": "name", "fieldtype": "Link", "width": 280},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 120},
	]

	columns.extend(period_columns)

	return columns


def get_period_date_ranges(filters):
	from dateutil.relativedelta import relativedelta

	from_date = round_down_to_nearest_frequency(filters.from_date, filters.range)
	to_date = getdate(filters.to_date)

	increment = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(filters.range, 1)

	periodic_daterange = []
	for _dummy in range(1, 53, increment):
		if filters.range == "Weekly":
			period_end_date = from_date + relativedelta(days=6)
		else:
			period_end_date = from_date + relativedelta(months=increment, days=-1)

		if period_end_date > to_date:
			period_end_date = to_date
		periodic_daterange.append([from_date, period_end_date])

		from_date = period_end_date + relativedelta(days=1)
		if period_end_date == to_date:
			break

	return periodic_daterange


def round_down_to_nearest_frequency(date: str, frequency: str) -> datetime.datetime:
	"""Rounds down the date to nearest frequency unit.
	example:

	>>> round_down_to_nearest_frequency("2021-02-21", "Monthly")
	datetime.datetime(2021, 2, 1)

	>>> round_down_to_nearest_frequency("2021-08-21", "Yearly")
	datetime.datetime(2021, 1, 1)
	"""

	def _get_first_day_of_fiscal_year(date):
		fiscal_year = get_fiscal_year(date)
		return fiscal_year and fiscal_year[1] or date

	round_down_function = {
		"Monthly": get_first_day_of_month,
		"Quarterly": get_quarter_start,
		"Weekly": get_first_day_of_week,
		"Yearly": _get_first_day_of_fiscal_year,
	}.get(frequency, getdate)
	return round_down_function(date)


def get_period(posting_date, filters):
	months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

	if filters.range == "Weekly":
		period = _("Week {0} {1}").format(str(posting_date.isocalendar()[1]), str(posting_date.year))
	elif filters.range == "Monthly":
		period = _(str(months[posting_date.month - 1])) + " " + str(posting_date.year)
	elif filters.range == "Quarterly":
		period = _("Quarter {0} {1}").format(str(((posting_date.month - 1) // 3) + 1), str(posting_date.year))
	else:
		year = get_fiscal_year(posting_date, company=filters.company)
		period = str(year[2])

	return period


def get_periodic_data(entry, filters):
	"""Structured as:
	Item 1
	        - Balance (updated and carried forward):
	                        - qty: {warehouse: bal_qty}
	                        - value: {warehouse: bal_value}
	        - Jun 2021 (snapshot of balance at end of this period)
	                        - qty: {warehouse: bal_qty}
	                        - value: {warehouse: bal_value}
	        - Jul 2021 (snapshot of balance at end of this period)
	                        - qty: {warehouse: bal_qty}
	                        - value: {warehouse: bal_value}
	Item 2
	        ...

	Both qty and value running balances are tracked simultaneously (instead of the
	original Stock Analytics' single either/or metric) so that a per-period average
	price (value / qty) can be derived downstream in get_data().
	"""

	expected_ranges = get_period_date_ranges(filters)
	expected_periods = []
	for _start_date, end_date in expected_ranges:
		expected_periods.append(get_period(end_date, filters))

	periodic_data = {}
	for d in entry:
		period = get_period(d.posting_date, filters)

		fill_intermediate_periods(periodic_data, d.item_code, period, expected_periods)

		item_bucket = periodic_data.setdefault(d.item_code, {})
		balance = item_bucket.setdefault("balance", {"qty": {}, "value": {}})

		if not item_bucket.get(period):
			item_bucket[period] = {
				"qty": balance["qty"].copy(),
				"value": balance["value"].copy(),
			}

		prev_bal_qty = balance["qty"].get(d.warehouse, 0.0)
		prev_bal_value = balance["value"].get(d.warehouse, 0.0)

		if d.voucher_type == "Stock Reconciliation" and not d.batch_no:
			qty_diff = d.qty_after_transaction - prev_bal_qty
			value_diff = d.stock_value - prev_bal_value
		else:
			qty_diff = d.actual_qty
			value_diff = d.stock_value_difference

		balance["qty"][d.warehouse] = prev_bal_qty + qty_diff
		balance["value"][d.warehouse] = prev_bal_value + value_diff

		item_bucket[period]["qty"][d.warehouse] = balance["qty"][d.warehouse]
		item_bucket[period]["value"][d.warehouse] = balance["value"][d.warehouse]

	return periodic_data


def fill_intermediate_periods(
	periodic_data, item_code: str, current_period: str, all_periods: list[str]
) -> None:
	"""There might be intermediate periods where no stock ledger entry exists, copy previous data.

	Previous data is ONLY copied if period falls in report range and before period being processed currently.

	args:
	        current_period: process till this period (exclusive)
	        all_periods: all periods expected in report via filters
	        periodic_data: report's periodic data
	        item_code: item_code being processed
	"""

	previous_period_data = None
	for period in all_periods:
		if period == current_period:
			return

		item_bucket = periodic_data.get(item_code)
		if item_bucket and not item_bucket.get(period) and previous_period_data:
			item_bucket[period] = {
				"qty": previous_period_data["qty"].copy(),
				"value": previous_period_data["value"].copy(),
			}

		previous_period_data = periodic_data.get(item_code, {}).get(period)


def get_data(filters):
	data = []
	items = get_items(filters)
	sle = get_stock_ledger_entries(filters, items)
	item_details = get_item_details(items, sle)
	periodic_data = get_periodic_data(sle, filters)
	ranges = get_period_date_ranges(filters)

	today = getdate()

	for _dummy, item_data in item_details.items():
		row = {
			"name": item_data.name,
			"uom": item_data.stock_uom,
		}
		previous_qty = 0.0
		previous_value = 0.0
		for start_date, end_date in ranges:
			period = get_period(end_date, filters)
			period_key = scrub(period)
			period_data = periodic_data.get(item_data.name, {}).get(period)

			if period_data:
				total_qty = sum(period_data["qty"].values())
				total_value = sum(period_data["value"].values())
				previous_qty = total_qty
				previous_value = total_value
			elif today >= start_date:
				total_qty = previous_qty
				total_value = previous_value
			else:
				total_qty = None
				total_value = None

			row[f"{period_key}_qty"] = total_qty
			row[f"{period_key}_total"] = total_value
			row[f"{period_key}_price"] = (total_value / total_qty) if total_qty else None

		data.append(row)

	return data


def get_items(filters):
	"Get items based on item code."
	if item_code := filters.get("item_code"):
		return [item_code]
	else:
		item_filters = {"is_stock_item": 1}
		return frappe.get_all("Item", filters=item_filters, pluck="name", order_by=None)


def get_stock_ledger_entries(filters, items):
	sle = frappe.qb.DocType("Stock Ledger Entry")

	query = (
		frappe.qb.from_(sle)
		.select(
			sle.item_code,
			sle.warehouse,
			sle.posting_date,
			sle.actual_qty,
			sle.valuation_rate,
			sle.company,
			sle.voucher_type,
			sle.qty_after_transaction,
			sle.stock_value_difference,
			sle.item_code.as_("name"),
			sle.voucher_no,
			sle.stock_value,
			sle.batch_no,
		)
		.where((sle.docstatus < 2) & (sle.is_cancelled == 0))
		.orderby(sle.posting_datetime)
		.orderby(sle.creation)
	)

	if items:
		query = query.where(sle.item_code.isin(items))

	query = apply_conditions(query, filters)
	return query.run(as_dict=True)


def apply_conditions(query, filters):
	sle = frappe.qb.DocType("Stock Ledger Entry")
	warehouse_table = frappe.qb.DocType("Warehouse")

	if not filters.get("from_date"):
		frappe.throw(_("'From Date' is required"))

	if to_date := filters.get("to_date"):
		to_date = get_datetime(str(to_date) + " 23:59:59")
		query = query.where(sle.posting_datetime <= to_date)
	else:
		frappe.throw(_("'To Date' is required"))

	if company := filters.get("company"):
		query = query.where(sle.company == company)

	if filters.get("warehouse"):
		query = apply_warehouse_filter(query, sle, filters)
	elif warehouse_type := filters.get("warehouse_type"):
		query = (
			query.join(warehouse_table)
			.on(warehouse_table.name == sle.warehouse)
			.where(warehouse_table.warehouse_type == warehouse_type)
		)

	return query


def get_item_details(items, sle):
	item_details = {}
	if not items:
		items = list(set(d.item_code for d in sle))

	if not items:
		return item_details

	item_table = frappe.qb.DocType("Item")

	query = (
		frappe.qb.from_(item_table)
		.select(
			item_table.name,
			item_table.stock_uom,
		)
		.where(item_table.name.isin(items))
	)

	result = query.run(as_dict=1)

	for item_table in result:
		item_details.setdefault(item_table.name, item_table)

	return item_details
