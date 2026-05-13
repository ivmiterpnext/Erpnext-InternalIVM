frappe.ui.form.on('Stock Entry', {
	refresh: function(frm) {
		if (frm.doc.custom_warehouse_request) {
			frm.add_custom_button(__('Warehouse Request'), function() {
				frappe.set_route('Form', 'Warehouse Request', frm.doc.custom_warehouse_request);
			}, __('View'));
		}
	}
});
