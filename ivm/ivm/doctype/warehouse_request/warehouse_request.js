// Copyright (c) 2023, korecent and contributors
// For license information, please see license.txt

frappe.ui.form.on('Warehouse Request', {
	refresh: function(frm) {
		// Add button to open item scanner page only if request_reason contains "Build"
		if (!frm.is_new() && frm.doc.request_reason && frm.doc.request_reason.includes('Build')) {
			// Check if stock entries already exist for this WR
			frappe.call({
				method: 'ivm.api.has_stock_entries_for_warehouse_request',
				args: {
					warehouse_request: frm.doc.name
				},
				callback: function(r) {
					if (!r.message) {
						// No stock entries exist, show the button
						frm.add_custom_button(__('Begin Picking'), function() {
							window.location.href = `/app/item_scanner?warehouse_request=${encodeURIComponent(frm.doc.name)}`;
						}, __('Stock'));
					} else {
						// Stock entries already exist, show info message
						frm.add_custom_button(__('Picking Completed'), function() {
							frappe.msgprint({
								title: __('Already Picked'),
								message: __('Items have already been picked for this Warehouse Request. Check the Stock Ledger for transfer details.'),
								indicator: 'blue'
							});
						}, __('Stock'));
					}
				}
			});
		}
	}
});
