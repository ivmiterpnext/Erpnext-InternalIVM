# Copyright (c) 2025, Dev and contributors
# For license information, please see license.txt

from ivm.ivm.utils.base_virtual_doctype import BaseVirtualDoctype


class MachineFee(BaseVirtualDoctype):
	API_TYPE = "icorp"
	SORT_FIELD_MAP = { "name": "id" }
	endpoint = "ClientContract/Fee/MachineFee"
