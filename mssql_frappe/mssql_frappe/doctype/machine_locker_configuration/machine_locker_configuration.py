# machine_locker_configuration.py

import frappe
from urllib.parse import quote_plus
from frappe.model.document import Document
from mssql_frappe.utils.api_utils import *
from mssql_frappe.utils.filter_utils import filters_to_query_params
from mssql_frappe.utils.case_utils import api_items_to_frappe_dict  # if you use it below

def _resolve_machine_name_from_board(value: str | int | None) -> str | None:
	"""Translate Board ID -> in_use_machine_name via external API.
	If value is already a machine name (or lookup fails), just return value.
	"""
	if not value:
		return value

	board_id = str(value).strip()
	cache_key = f"boardid->in_use_machine_name::{board_id}"
	cached = frappe.cache().get_value(cache_key)
	if cached is not None:
		return cached or value

	try:
		endpoint = f"SV/Board/GetById?Id={quote_plus(board_id)}"
		resp = icorp_api_get(endpoint)
		data = resp.get("data") or {}
		# Endpoint may return dict or list; normalize
		if isinstance(data, list):
			data = next((r for r in data if str(r.get("id")) == board_id), data[0] if data else {})

		machine_name = data.get("in_use_machine_name") or data.get("machine_name")
		# Cache even negatives briefly to avoid hammering
		frappe.cache().set_value(cache_key, machine_name or "", expires_in_sec=300)
		return machine_name or value
	except Exception:
		frappe.log_error(frappe.get_traceback(), "MLC._resolve_machine_name_from_board error")
		return value


class MachineLockerConfiguration(Document):
	def db_insert(self, *args, **kwargs):
		raise NotImplementedError

	def load_from_db(self):
		raise NotImplementedError

	def db_update(self):
		raise NotImplementedError

	def delete(self):
		raise NotImplementedError

	@staticmethod
	def get_list(filters=None, page_length=20, start=0, order_by=None, **kwargs):
		page = (start // page_length) + 1

		# Translate dashboard-provided Board ID -> machine_name
		if isinstance(filters, dict) and "in_use_machine_name" in filters:
			val = _resolve_machine_name_from_board(filters["in_use_machine_name"])
			filters["machine_name"] = val
			del filters["in_use_machine_name"]

		elif isinstance(filters, (list, tuple)):
			new_filters = []
			for f in filters:
				if isinstance(f, (list, tuple)) and len(f) >= 4 and f[1] == "in_use_machine_name":
					op, rhs = f[2], f[3]
					rhs = _resolve_machine_name_from_board(rhs)
					new_filters.append((f[0], "machine_name", op, rhs))
				else:
					new_filters.append(f)
			filters = new_filters

		filter_query = filters_to_query_params(filters)

		endpoint = f"SV/MachineLockerConfiguration?page={page}&pageSize={page_length}"
		if filter_query:
			endpoint += f"&{filter_query}"

		try:
			result = icorp_api_get(endpoint)
			items = result.get("data", [])
			return api_items_to_frappe_dict(items, key_field="id")
		except Exception:
			frappe.log_error(frappe.get_traceback(), "MachineLockerConfiguration.get_list error")
			return []

	@staticmethod
	def get_count(filters=None, **kwargs):
		pass

	@staticmethod
	def get_stats(**kwargs):
		pass
