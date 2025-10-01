frappe.listview_settings['Smart Screen'] = {
	get_indicator(doc) {
		return ['\u00A0', doc.status_code, ['status_code', '=', doc.status_code]];
	},
};
