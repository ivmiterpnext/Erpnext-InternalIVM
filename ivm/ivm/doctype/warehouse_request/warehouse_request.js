// Copyright (c) 2023, korecent and contributors
// For license information, please see license.txt

frappe.ui.form.on('Warehouse Request', {
	setup: function(frm) {
		frm.set_query('source_build_request', function() {
			return {
				filters: {
					related_project: frm.doc.related_project,
					request_reason: ['like', 'Build%'],
					status: 'Crated - Ready to Ship'
				}
			};
		});
	},

	onload: function(frm) {
		if (!frm.is_new()) {
			frm._server_status = frm.doc.status;
		}
	},

	refresh: function(frm) {
		if (frm.is_new() || !frm.doc.request_reason) return;

		// Update the cached server status on every refresh (which fires after save too)
		frm._server_status = frm.doc.status;

		var is_pick_request = frm.doc.request_reason.includes('Build') || frm.doc.request_reason == 'Shipping Request';
		if (!is_pick_request) return;

		// Shipping Requests linked to a Build skip the Item Scanner —
		// just show a Delivery Note button if one exists
		if (frm.doc.request_reason == 'Shipping Request' && frm.doc.source_build_request) {
			frappe.db.get_value('Delivery Note',
				{custom_related_warehouse_request: frm.doc.name, docstatus: ['!=', 2]},
				'name',
				function(r) {
					if (r && r.name) {
						frm.add_custom_button(__('Delivery Note'), function() {
							frappe.set_route('Form', 'Delivery Note', r.name);
						}, __('View'));
					}
				}
			);
			return;
		}

		frappe.call({
			method: 'ivm.warehouse.services.warehouse_request.get_warehouse_request_linked_docs',
			args: { warehouse_request: frm.doc.name },
			callback: function(r) {
				if (!r.message) return;
				var docs = r.message;

				if (!docs.pick_list) {
					frm.add_custom_button(__('Begin Picking'), function() {
						frappe.set_route('item_scanner', { warehouse_request: frm.doc.name });
					}, __('Stock'));
					return;
				}

				if (!docs.pick_list_submitted) {
					frm.add_custom_button(__('Continue Picking'), function() {
						frappe.set_route('item_scanner', { warehouse_request: frm.doc.name });
					}, __('Stock'));
					frm.add_custom_button(__('Reset Pick List'), function() {
						frappe.confirm(
							__('Delete the current draft Pick List and start fresh?'),
							function() {
								frappe.call({
									method: 'ivm.warehouse.services.warehouse_request.reset_warehouse_request_pick_list',
									args: { warehouse_request: frm.doc.name },
									callback: function(res) {
										if (res.message && res.message.success) {
											frm.reload_doc();
										} else {
											frappe.msgprint(res.message && res.message.message || __('Could not reset pick list'));
										}
									}
								});
							}
						);
					}, __('Stock'));
					return;
				}

				frm.add_custom_button(__('Pick List'), function() {
					frappe.set_route('Form', 'Pick List', docs.pick_list);
				}, __('View'));

				if (docs.stock_entry) {
					frm.add_custom_button(__('Stock Entry'), function() {
						frappe.set_route('Form', 'Stock Entry', docs.stock_entry);
					}, __('View'));
				}

				if (docs.delivery_note) {
					frm.add_custom_button(__('Delivery Note'), function() {
						frappe.set_route('Form', 'Delivery Note', docs.delivery_note);
					}, __('View'));
				}
			}
		});
	},

	after_save: function(frm) {
		if (!frm.doc.request_reason || !frm.doc.request_reason.includes('Build')) return;
		if (frm.doc.status !== 'Crated - Ready to Ship') return;

		// Only prompt if status actually changed to "Crated - Ready to Ship" on this save
		if (frm._server_status === 'Crated - Ready to Ship') return;

		frappe.confirm(
			__('Create a Shipping Request for this build?'),
			function() {
				frappe.call({
					method: 'ivm.warehouse.services.warehouse_request.create_shipping_request_from_build',
					args: { build_warehouse_request: frm.doc.name },
					callback: function(r) {
						if (r.message) {
							frappe.set_route('Form', 'Warehouse Request', r.message);
						}
					}
				});
			}
		);
	}
});
