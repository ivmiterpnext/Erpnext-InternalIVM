frappe.ui.form.on('Delivery Note', {
	setup: function(frm) {
		// Customize Warehouse Request link field to show ID and subject
		frm.set_query('custom_related_warehouse_request', function() {
			return {
				query: 'ivm.warehouse.services.warehouse_request.warehouse_request_query'
			};
		});
	},
	
	custom_related_warehouse_request: function(frm) {
		// Auto-fetch items whenever warehouse request is selected or changed
		if (frm.doc.custom_related_warehouse_request) {
			frappe.call({
				method: 'ivm.warehouse.services.stock_entry.get_stock_entry_items_from_warehouse_request',
				args: {
					warehouse_request: frm.doc.custom_related_warehouse_request
				},
				callback: function(r) {
					if (r.message && r.message.length > 0) {
						// Clear existing items
						frm.clear_table('items');
						
						// Add items from warehouse request
						r.message.forEach(function(item) {
							var row = frm.add_child('items');
							row.item_code = item.item_code;
							row.item_name = item.item_name;
							row.description = item.description;
							row.qty = item.qty;
							row.uom = item.uom;
							row.stock_uom = item.stock_uom;
							row.conversion_factor = item.conversion_factor;
							row.warehouse = item.warehouse;
							row.rate = item.rate || 0;
							row.price_list_rate = item.price_list_rate || 0;
						});
						
						frm.refresh_field('items');
						frappe.show_alert({
							message: __('Items loaded from Warehouse Request {0}', [frm.doc.custom_related_warehouse_request]),
							indicator: 'green'
						}, 3);
					} else {
						frappe.msgprint({
							title: __('No Items Found'),
							message: __('No items found for Warehouse Request {0}', [frm.doc.custom_related_warehouse_request]),
							indicator: 'orange'
						});
					}
				},
				error: function(r) {
					frappe.msgprint({
						title: __('Error'),
						message: __('Could not fetch items from Warehouse Request'),
						indicator: 'red'
					});
				}
			});
		}
	}
});
