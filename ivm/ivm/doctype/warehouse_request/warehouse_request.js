// Copyright (c) 2023, korecent and contributors
// For license information, please see license.txt

frappe.ui.form.on('Warehouse Request', {
	refresh: function(frm) {
		// Add button to open item scanner page for Build or Shipping requests
		if (!frm.is_new() && frm.doc.request_reason &&
		    (frm.doc.request_reason.includes('Build') || frm.doc.request_reason == 'Shipping Request')) {

			if (frm.doc.pick_list) {
				frappe.db.get_value('Pick List', frm.doc.pick_list, 'docstatus', function(r) {
					if (r && r.docstatus === 1) {
						frappe.db.get_value('Stock Entry', { pick_list: frm.doc.pick_list }, 'name', function(se) {
							if (se && se.name) {
								frm.add_custom_button(__('View Stock Entry'), function() {
									frappe.set_route('Form', 'Stock Entry', se.name);
								}, __('Stock'));
							}
						});
					} else {
						frm.add_custom_button(__('Continue Picking'), function() {
							window.location.href = `/app/item_scanner?warehouse_request=${encodeURIComponent(frm.doc.name)}`;
						}, __('Stock'));
						frm.add_custom_button(__('Reset Pick List'), function() {
							frappe.confirm(
								__('Delete the current draft Pick List and start fresh?'),
								function() {
									frappe.call({
										method: 'ivm.warehouse.services.warehouse_request.reset_warehouse_request_pick_list',
										args: { warehouse_request: frm.doc.name },
										callback: function(r) {
											if (r.message && r.message.success) {
												frm.reload_doc();
											} else {
												frappe.msgprint(r.message && r.message.message || __('Could not reset pick list'));
											}
										}
									});
								}
							);
						}, __('Stock'));
					}
				});
			} else {
				frm.add_custom_button(__('Begin Picking'), function() {
					window.location.href = `/app/item_scanner?warehouse_request=${encodeURIComponent(frm.doc.name)}`;
				}, __('Stock'));
			}
		}
	}
});
