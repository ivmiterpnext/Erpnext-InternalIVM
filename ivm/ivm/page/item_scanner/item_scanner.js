frappe.pages['item_scanner'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Item Scanner',
		single_column: true
	});

	new ItemScanner(page);
};

class ItemScanner {
	constructor(page) {
		this.page = page;
		this.wrapper = $(this.page.body);
		this.scanned_items = [];
		this.warehouse_request = frappe.utils.get_url_arg('warehouse_request');
		
		if (!this.warehouse_request) {
			frappe.msgprint('No Warehouse Request specified');
			frappe.set_route('List', 'Warehouse Request');
			return;
		}
		
		this.init();
	}

	init() {
		this.wrapper.html(frappe.render_template('item_scanner'));
		this.load_barcode_library();
		this.setup_barcode_field();
		this.setup_events();
		this.load_warehouse_request();
		this.focus_barcode_input();
	}
	
	load_barcode_library() {
		// Load html5-qrcode library for camera scanning
		if (!window.Html5Qrcode) {
			const script = document.createElement('script');
			script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
			script.async = true;
			document.head.appendChild(script);
		}
	}
	
	setup_barcode_field() {
		const me = this;
		
		// Create barcode field using Frappe's control
		this.barcode_field = frappe.ui.form.make_control({
			parent: $('#barcode-field'),
			df: {
				fieldtype: 'Data',
				label: __('Scan Barcode'),
				fieldname: 'barcode',
				placeholder: __('Scan or enter barcode...'),
				description: __('Scan item barcode - source warehouse will be auto-detected')
			},
			render_input: true
		});
		
		// Handle Enter key for barcode scanning
		this.barcode_field.$input.on('keydown', function(e) {
			if (e.which === 13) { // Enter key
				e.preventDefault();
				const barcode = me.barcode_field.get_value();
				if (barcode && barcode.trim()) {
					me.lookup_item(barcode.trim());
					me.barcode_field.set_value('');
					me.focus_barcode_input();
				}
			}
		});
		
		// Add camera scanner button
		this.barcode_field.$wrapper.find('.control-input-wrapper').css('position', 'relative');
		const $camera_btn = $(`
			<button class="btn btn-xs btn-default" style="position: absolute; right: 5px; top: 50%; transform: translateY(-50%); padding: 2px 6px;" title="${__('Scan with Camera')}">
				<svg class="icon icon-sm" style="width: 14px; height: 14px;">
					<use href="#icon-camera"></use>
				</svg>
			</button>
		`);
		
		$camera_btn.on('click', function(e) {
			e.preventDefault();
			e.stopPropagation();
			me.show_camera_scanner();
		});
		
		this.barcode_field.$wrapper.find('.control-input').append($camera_btn);
	}
	
	show_camera_scanner() {
		const me = this;
		
		// Check if library is loaded
		if (typeof Html5Qrcode === 'undefined') {
			frappe.msgprint({
				title: __('Loading Scanner'),
				message: __('Barcode scanner is loading. Please try again in a moment.'),
				indicator: 'orange'
			});
			return;
		}
		
		// Show modal
		$('#camera-scanner-modal').show();
		
		// Initialize scanner
		const html5QrcodeScanner = new Html5Qrcode("camera-reader");
		
		// Simple configuration for linear barcodes
		const config = {
			fps: 10,
			qrbox: { width: 500, height: 150 }
		};
		
		// Start scanning
		html5QrcodeScanner.start(
			{ facingMode: "environment" },
			config,
			(decodedText, decodedResult) => {
				// Success - barcode scanned
				$('#scan-result').text('Scanned: ' + decodedText).show();
				
				// Process the barcode
				me.lookup_item(decodedText.trim());
				me.barcode_field.set_value('');
				
				// Stop scanner and close modal after short delay
				setTimeout(() => {
					html5QrcodeScanner.stop().then(() => {
						$('#camera-scanner-modal').hide();
						$('#scan-result').hide();
						me.focus_barcode_input();
					}).catch(err => {
						console.error('Error stopping scanner:', err);
					});
				}, 1000);
			},
			(errorMessage) => {
				// Scanning error (not necessarily fatal)
				// Just log it and continue scanning
			}
		).catch(err => {
			frappe.msgprint({
				title: __('Camera Error'),
				message: __('Could not access camera. Please ensure camera permissions are granted.'),
				indicator: 'red'
			});
			$('#camera-scanner-modal').hide();
		});
		
		// Close button handler
		$('#close-scanner').off('click').on('click', function() {
			html5QrcodeScanner.stop().then(() => {
				$('#camera-scanner-modal').hide();
				me.focus_barcode_input();
			}).catch(err => {
				console.error('Error stopping scanner:', err);
				$('#camera-scanner-modal').hide();
			});
		});
	}

	setup_events() {
		const me = this;
		
		// Submit button
		$('#submit-btn').click(() => this.create_stock_entry());
		
		// Cancel button
		$('#cancel-btn').click(() => {
			frappe.set_route('Form', 'Warehouse Request', this.warehouse_request);
		});
		
		// Keep focus on barcode input
		$(document).on('click', function(e) {
			if (!$(e.target).is('input, button, a, select')) {
				me.focus_barcode_input();
			}
		});
	}

	focus_barcode_input() {
		setTimeout(() => {
			if (this.barcode_field) {
				this.barcode_field.$input.focus();
			}
		}, 100);
	}

	load_warehouse_request() {
		frappe.call({
			method: 'frappe.client.get',
			args: {
				doctype: 'Warehouse Request',
				name: this.warehouse_request
			},
			callback: (r) => {
				if (r.message) {
					$('#wr-name').text(r.message.name);
					if (r.message.subject) {
						$('#wr-subject').text('- ' + r.message.subject);
					}
					$('#wr-status').text(r.message.status || 'Open');
				}
			}
		});
	}

	lookup_item(barcode) {
		// Use custom API method to bypass Item Barcode child table permission issues
		frappe.call({
			method: 'ivm.api.lookup_item_by_barcode',
			args: {
				barcode: barcode
			},
			callback: (r) => {
				if (r.message) {
					this.fetch_item_details(r.message);
				} else {
					frappe.show_alert({
						message: `Item "${barcode}" not found`,
						indicator: 'red'
					}, 5);
					this.play_error_sound();
				}
			}
		});
	}

	fetch_item_details(item_code) {
		frappe.call({
			method: 'ivm.api.get_item_with_warehouse',
			args: {
				item_code: item_code,
				parent_warehouse: 'Warehouse - I'
			},
			callback: (r) => {
				if (r.message) {
					if (!r.message.warehouses || r.message.warehouses.length === 0) {
						frappe.show_alert({
							message: `${r.message.item_name} has no stock in any warehouse`,
							indicator: 'orange'
						}, 5);
						this.play_error_sound();
						return;
					}
					
					const success = this.add_item_from_scan(r.message);
					
					if (success) {
						const total_available = r.message.warehouses.reduce((sum, w) => sum + w.available_qty, 0);
						frappe.show_alert({
							message: `Added: ${r.message.item_name} (${total_available} available)`,
							indicator: 'green'
						}, 3);
						this.play_success_sound();
					}
				} else {
					frappe.show_alert({
						message: `Item ${item_code} not found in any warehouse`,
						indicator: 'orange'
					}, 5);
					this.play_error_sound();
				}
			}
		});
	}

	add_item_from_scan(item_data) {
		// When scanning, add 1 qty from the first available warehouse
		const first_warehouse = item_data.warehouses[0];
		
		// Check if this item-warehouse combination already exists
		const existing = this.scanned_items.find(i => 
			i.item_code === item_data.item_code && 
			i.source_warehouse === first_warehouse.warehouse
		);
		
		if (existing) {
			// Check if we can increment
			if (existing.qty < first_warehouse.available_qty) {
				existing.qty += 1;
			} else {
				// Current warehouse exhausted, try next warehouse
				const next_warehouse = item_data.warehouses.find(w => {
					const existing_in_wh = this.scanned_items.find(i => 
						i.item_code === item_data.item_code && 
						i.source_warehouse === w.warehouse
					);
					return !existing_in_wh || existing_in_wh.qty < w.available_qty;
				});
				
				if (next_warehouse) {
					this.add_new_item_row(item_data, next_warehouse.warehouse, next_warehouse.available_qty, 1);
				} else {
					frappe.show_alert({
						message: `No more stock available for ${item_data.item_name}`,
						indicator: 'orange'
					}, 5);
					this.play_error_sound();
					return false; // Failed to add
				}
			}
		} else {
			// Add new row
			this.add_new_item_row(item_data, first_warehouse.warehouse, first_warehouse.available_qty, 1);
		}
		
		this.render_items();
		this.update_submit_button();
		return true; // Successfully added
	}
	
	add_new_item_row(item_data, warehouse, available_qty, qty) {
		this.scanned_items.push({
			item_code: item_data.item_code,
			item_name: item_data.item_name,
			qty: qty,
			uom: item_data.stock_uom,
			source_warehouse: warehouse,
			available_qty: available_qty
		});
	}

	render_items() {
		const tbody = $('#items-tbody');
		
		if (this.scanned_items.length === 0) {
			tbody.html(`
				<tr class="text-muted">
					<td colspan="7" class="text-center">No items scanned yet</td>
				</tr>
			`);
			return;
		}
		
		tbody.empty();
		this.scanned_items.forEach((item, index) => {
			const qty_class = item.qty > item.available_qty ? 'text-danger' : '';
			tbody.append(`
				<tr>
					<td>${item.item_code}</td>
					<td>${item.item_name}</td>
					<td><span class="text-muted">${item.source_warehouse || 'Not found'}</span></td>
					<td><span class="badge badge-info">${item.available_qty || 0}</span></td>
					<td>
						<input type="number" 
							class="form-control input-sm ${qty_class}" 
							value="${item.qty}" 
							min="1" 
							max="${item.available_qty}"
							data-index="${index}"
							onchange="cur_page.item_scanner.update_qty(${index}, this.value)"
							style="width: 80px;">
					</td>
					<td>${item.uom}</td>
					<td>
						<button class="btn btn-xs btn-danger" onclick="cur_page.item_scanner.remove_item(${index})">
							<i class="fa fa-trash"></i>
						</button>
					</td>
				</tr>
			`);
		});
	}

	update_qty(index, value) {
		const qty = parseInt(value);
		const item = this.scanned_items[index];
		
		if (qty <= 0) {
			frappe.msgprint('Quantity must be greater than 0');
			this.render_items();
			return;
		}
		
		if (qty > item.available_qty) {
			frappe.confirm(
				`Only ${item.available_qty} available in ${item.source_warehouse}. Do you want to set quantity to ${item.available_qty}?`,
				() => {
					item.qty = item.available_qty;
					this.render_items();
				},
				() => {
					this.render_items(); // Reset to previous value
				}
			);
		} else {
			item.qty = qty;
			this.render_items();
		}
	}

	remove_item(index) {
		this.scanned_items.splice(index, 1);
		this.render_items();
		this.update_submit_button();
		this.focus_barcode_input();
	}

	update_submit_button() {
		const has_items = this.scanned_items.length > 0;
		const all_have_warehouses = this.scanned_items.every(item => item.source_warehouse);
		const all_valid_qty = this.scanned_items.every(item => item.qty > 0 && item.qty <= item.available_qty);
		$('#submit-btn').prop('disabled', !(has_items && all_have_warehouses && all_valid_qty));
	}

	create_stock_entry() {
		const target_warehouse = $('#target-warehouse').val();
		
		if (this.scanned_items.length === 0) {
			frappe.msgprint('Please scan at least one item');
			return;
		}
		
		const items_without_warehouse = this.scanned_items.filter(i => !i.source_warehouse);
		if (items_without_warehouse.length > 0) {
			frappe.msgprint('Some items do not have a source warehouse detected');
			return;
		}
		
		// Check for quantity overages
		const items_over_stock = this.scanned_items.filter(i => i.qty > i.available_qty);
		if (items_over_stock.length > 0) {
			const item_names = items_over_stock.map(i => 
				`${i.item_name} (need ${i.qty}, have ${i.available_qty})`
			).join(', ');
			frappe.msgprint(`Cannot proceed: ${item_names} exceed available stock`);
			return;
		}
		
		const total_items = this.scanned_items.reduce((sum, item) => sum + item.qty, 0);
		
		frappe.confirm(
			`Create Material Transfer for ${total_items} item(s) from ${this.scanned_items.length} warehouse location(s)?`,
			() => {
				frappe.call({
					method: 'ivm.api.create_stock_entry_from_scan',
					args: {
						warehouse_request: this.warehouse_request,
						items: this.scanned_items,
						target_warehouse: target_warehouse
					},
					callback: (r) => {
						if (r.message) {
							frappe.show_alert({
								message: `Stock Entry ${r.message} created successfully`,
								indicator: 'green'
							}, 5);
							
							frappe.set_route('/desk/dashboard-view/Stock');
						}
					}
				});
			}
		);
	}

	play_success_sound() {
		// Optional: add beep sound for success
		// frappe.utils.play_sound('submit');
	}

	play_error_sound() {
		// Optional: add beep sound for error
		// frappe.utils.play_sound('error');
	}
}

// Make the scanner available globally for inline event handlers
frappe.pages['item_scanner'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	cur_page.item_scanner = page.item_scanner || new ItemScanner(page);
};
