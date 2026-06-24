frappe.pages['item_scanner'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Item Scanner',
		single_column: true
	});

	page.item_scanner = new ItemScanner(page);
};

class ItemScanner {
	constructor(page) {
		this.page = page;
		this.wrapper = $(this.page.body);
		this.warehouse_request = frappe.urllib.get_arg('warehouse_request')
			|| (frappe.route_options && frappe.route_options.warehouse_request);
		this.pick_list = null;
		this.scanned_items = []; // mirrors Pick List locations for rendering

		if (!this.warehouse_request) {
			frappe.msgprint('No Warehouse Request specified');
			frappe.set_route('List', 'Warehouse Request');
			return;
		}

		this.init();
	}

	init() {
		this.wrapper.html(frappe.render_template('item_scanner', {}));
		this.load_barcode_library();
		this.setup_target_warehouse_field();
		this.setup_barcode_field();
		this.setup_events();
		this.load_warehouse_request();
		this.load_pick_list();
	}

	load_barcode_library() {
		if (!window.Html5Qrcode) {
			const script = document.createElement('script');
			script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
			script.async = true;
			document.head.appendChild(script);
		}
	}

	setup_target_warehouse_field() {
		const me = this;
		this.target_warehouse_field = frappe.ui.form.make_control({
			parent: $('#target-warehouse-field'),
			df: {
				fieldtype: 'Link',
				label: __('Target Warehouse'),
				fieldname: 'target_warehouse',
				options: 'Warehouse',
				placeholder: __('Select target warehouse...'),
				onchange: function() {
					const val = me.target_warehouse_field.get_value();
					if (val && me.pick_list) {
						frappe.db.set_value('Pick List', me.pick_list, 'parent_warehouse', val);
					}
				}
			},
			render_input: true
		});
	}

	setup_barcode_field() {
		const me = this;

		this.barcode_field = frappe.ui.form.make_control({
			parent: $('#barcode-field'),
			df: {
				fieldtype: 'Data',
				label: __('Scan Barcode'),
				fieldname: 'barcode',
				placeholder: __('Scan or enter barcode...'),
				description: __('Source warehouse will be auto-detected')
			},
			render_input: true
		});

		this.barcode_field.$input.on('keydown', function(e) {
			if (e.which === 13) {
				e.preventDefault();
				const barcode = me.barcode_field.get_value();
				if (barcode && barcode.trim()) {
					me.lookup_item(barcode.trim());
					me.barcode_field.set_value('');
					me.focus_barcode_input();
				}
			}
		});

		this.barcode_field.$wrapper.find('.control-input-wrapper').css('position', 'relative');
		this.$camera_btn = $(`
			<button class="btn btn-xs btn-default" style="position: absolute; right: 5px; top: 50%; transform: translateY(-50%); padding: 2px 6px;" title="${__('Scan with Camera')}">
				<svg class="icon icon-sm" style="width: 14px; height: 14px;">
					<use href="#icon-camera"></use>
				</svg>
			</button>
		`);

		this.$camera_btn.on('click', function(e) {
			e.preventDefault();
			e.stopPropagation();
			me.show_camera_scanner();
		});

		this.barcode_field.$wrapper.find('.control-input').append(this.$camera_btn);
	}

	show_camera_scanner() {
		const me = this;

		if (typeof Html5Qrcode === 'undefined') {
			frappe.msgprint({
				title: __('Loading Scanner'),
				message: __('Barcode scanner is loading. Please try again in a moment.'),
				indicator: 'orange'
			});
			return;
		}

		$('#camera-scanner-modal').show();

		const html5QrcodeScanner = new Html5Qrcode("camera-reader");
		const config = { fps: 10, qrbox: { width: 500, height: 150 } };

		html5QrcodeScanner.start(
			{ facingMode: "environment" },
			config,
			(decodedText) => {
				$('#scan-result').text('Scanned: ' + decodedText).show();
				me.lookup_item(decodedText.trim());
				me.barcode_field.set_value('');

				setTimeout(() => {
					html5QrcodeScanner.stop().then(() => {
						$('#camera-scanner-modal').hide();
						$('#scan-result').hide();
						me.focus_barcode_input();
					}).catch(err => console.error('Error stopping scanner:', err));
				}, 1000);
			},
			() => {}
		).catch(() => {
			frappe.msgprint({
				title: __('Camera Error'),
				message: __('Could not access camera. Please ensure camera permissions are granted.'),
				indicator: 'red'
			});
			$('#camera-scanner-modal').hide();
		});

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

		$('#submit-btn').click(() => this.submit_pick_list());

		$('#cancel-btn').click(() => {
			frappe.set_route('Form', 'Warehouse Request', this.warehouse_request);
		});

		$('#clear-btn').click(() => {
			if (!me.scanned_items.length) return;
			frappe.confirm(__('Remove all scanned items from the pick list?'), () => {
				frappe.call({
					method: 'ivm.warehouse.services.pick_list.clear_pick_list_items',
					args: { pick_list: me.pick_list },
					callback: (r) => {
						if (r.message && r.message.success) {
							me.scanned_items = [];
							me.render_items();
							me.update_submit_button();
							me.focus_barcode_input();
						}
					}
				});
			});
		});

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
			args: { doctype: 'Warehouse Request', name: this.warehouse_request },
			callback: (r) => {
				if (r.message) {
					$('#wr-name').text(r.message.name).attr('href', `/app/warehouse-request/${encodeURIComponent(r.message.name)}`);
					if (r.message.subject) {
						$('#wr-subject').text('- ' + r.message.subject);
					}
				}
			}
		});
	}

	load_pick_list() {
		frappe.call({
			method: 'ivm.warehouse.services.warehouse_request.get_or_create_warehouse_request_pick_list',
			args: { warehouse_request: this.warehouse_request },
			callback: (r) => {
				if (r.message) {
					this.pick_list = r.message.pick_list;
					this.pick_list_submitted = r.message.submitted || false;
					this.stock_entry = r.message.stock_entry || null;
					this.scanned_items = r.message.items || [];
					if (r.message.target_warehouse) {
						this.target_warehouse_field.set_value(r.message.target_warehouse);
					}
					const label = this.pick_list_submitted
						? `${this.pick_list} (Submitted)`
						: this.pick_list;
					$('#pick-list-name').text(label).attr('href', `/app/pick-list/${encodeURIComponent(this.pick_list)}`);
					if (this.pick_list_submitted) {
						this.disable_scanning();
					} else {
						this.render_items();
						this.update_submit_button();
						this.focus_barcode_input();
					}
				}
			}
		});
	}

	disable_scanning() {
		this.render_items();
		this.barcode_field.$input.prop('disabled', true);
		this.$camera_btn.prop('disabled', true);
		this.target_warehouse_field.$input.prop('disabled', true);
		$('#submit-btn').prop('disabled', true);
		$('#clear-btn').prop('disabled', true);
		const link = this.stock_entry
			? `<a href="/app/stock-entry/${this.stock_entry}">View Stock Entry</a>`
			: `<a href="/app/pick-list/${this.pick_list}">View Pick List</a>`;
		frappe.show_alert({ message: `Pick List already submitted. ${link}`, indicator: 'blue' }, 10);
	}

	lookup_item(barcode) {
		frappe.call({
			method: 'ivm.warehouse.services.barcode_manager.lookup_item_by_barcode',
			args: { barcode: barcode },
			callback: (r) => {
				if (r.message) {
					this.fetch_item_details(r.message);
				} else {
					frappe.show_alert({ message: `Item "${barcode}" not found`, indicator: 'red' }, 5);
					this.play_error_sound();
				}
			}
		});
	}

	fetch_item_details(item_code) {
		frappe.call({
			method: 'ivm.warehouse.services.inventory.get_item_with_warehouse',
			args: { item_code: item_code, parent_warehouse: 'All Warehouses - I' },
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
					this.add_item_from_scan(r.message);
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
		if (!this.pick_list) {
			frappe.show_alert({ message: 'Pick List not loaded yet, please wait', indicator: 'orange' }, 3);
			return;
		}

		for (const wh of item_data.warehouses) {
			const existing = this.scanned_items.find(i =>
				i.item_code === item_data.item_code && i.warehouse === wh.warehouse
			);
			if (!existing) {
				this._add_new_row(item_data, wh.warehouse, wh.available_qty, 1);
				return;
			}
			if (existing.qty < wh.available_qty) {
				this._update_item_qty(existing, existing.qty + 1);
				return;
			}
		}

		frappe.show_alert({
			message: `No more stock available for ${item_data.item_name}`,
			indicator: 'orange'
		}, 5);
		this.play_error_sound();
	}

	_add_new_row(item_data, warehouse, available_qty, qty) {
		frappe.call({
			method: 'ivm.warehouse.services.pick_list.add_item_to_pick_list',
			args: {
				pick_list: this.pick_list,
				item_code: item_data.item_code,
				warehouse: warehouse,
				qty: qty,
				item_name: item_data.item_name,
				uom: item_data.stock_uom
			},
			callback: (r) => {
				if (r.message) {
					this.scanned_items.push({
						row_name: r.message.row_name,
						item_code: item_data.item_code,
						item_name: item_data.item_name,
						warehouse: warehouse,
						available_qty: available_qty,
						qty: r.message.qty,
						uom: item_data.stock_uom
					});
					this.play_success_sound();
					this.render_items();
					this.update_submit_button();
				}
			}
		});
	}

	_update_item_qty(item, new_qty) {
		frappe.call({
			method: 'ivm.warehouse.services.pick_list.update_pick_list_item_qty',
			args: { pick_list: this.pick_list, row_name: item.row_name, qty: new_qty },
			callback: (r) => {
				if (r.message && r.message.success) {
					item.qty = new_qty;
					this.play_success_sound();
					this.render_items();
					this.update_submit_button();
				}
			}
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
		[...this.scanned_items].reverse().forEach((item) => {
			const index = this.scanned_items.indexOf(item);
			const qty_class = item.qty > item.available_qty ? 'text-danger' : '';
			tbody.append(`
				<tr>
					<td>${item.item_code}</td>
					<td>${item.item_name}</td>
					<td><span class="text-muted">${item.warehouse || 'Not found'}</span></td>
					<td class="text-center"><span class="badge badge-info">${item.available_qty || 0}</span></td>
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
					<td class="text-center">
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
				`Only ${item.available_qty} available in ${item.warehouse}. Set quantity to ${item.available_qty}?`,
				() => this._update_item_qty(item, item.available_qty),
				() => this.render_items()
			);
		} else {
			this._update_item_qty(item, qty);
		}
	}

	remove_item(index) {
		const item = this.scanned_items[index];
		frappe.call({
			method: 'ivm.warehouse.services.pick_list.remove_pick_list_item',
			args: { pick_list: this.pick_list, row_name: item.row_name },
			callback: (r) => {
				if (r.message && r.message.success) {
					this.scanned_items.splice(index, 1);
					this.render_items();
					this.update_submit_button();
					this.focus_barcode_input();
				}
			}
		});
	}

	update_submit_button() {
		const has_items = this.scanned_items.length > 0;
		const all_have_warehouses = this.scanned_items.every(item => item.warehouse);
		const all_valid_qty = this.scanned_items.every(item => item.qty > 0 && item.qty <= item.available_qty);
		$('#submit-btn').prop('disabled', !(has_items && all_have_warehouses && all_valid_qty));
	}

	submit_pick_list() {
		if (this.scanned_items.length === 0) {
			frappe.msgprint('Please scan at least one item');
			return;
		}

		const target_warehouse = this.target_warehouse_field && this.target_warehouse_field.get_value();
		if (!target_warehouse) {
			frappe.msgprint('Please select a Target Warehouse');
			return;
		}

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
			`Submit Pick List with ${total_items} total items across ${this.scanned_items.length} line(s)? You will be navigated to Stock Entry for review. Picked Items can be edited later via Stock Entry if necessary.`,
			() => {
				frappe.call({
					method: 'ivm.warehouse.services.pick_list.submit_pick_list',
					args: { pick_list: this.pick_list, target_warehouse: target_warehouse },
					callback: (r) => {
						if (r.message) {
							frappe.set_route('Form', 'Stock Entry', r.message.stock_entry);
						}
					}
				});
			}
		);
	}

	play_success_sound() {}
	play_error_sound() {}
}

frappe.pages['item_scanner'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	cur_page.item_scanner = page.item_scanner || new ItemScanner(page);
};
