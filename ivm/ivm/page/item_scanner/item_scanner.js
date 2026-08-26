frappe.pages['item_scanner'].on_page_load = function(wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Item Scanner',
		single_column: true
	});
};

class ItemScanner {
	constructor(page, warehouse_request) {
		this.page = page;
		this.wrapper = $(this.page.body);
		this.warehouse_request = warehouse_request;
		this.pick_list = null;
		this.scanned_items = []; // mirrors Pick List locations for rendering
		this.last_search_scope = 'All Warehouses - I';

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
				description: __('Items will be moved to this warehouse once the Pick List is submitted'),
			onchange: function() {
				const val = me.target_warehouse_field.get_value();
				if (val && me.pick_list) {
					frappe.call({
						method: 'frappe.client.set_value',
						args: {
							doctype: 'Pick List',
							name: me.pick_list,
							fieldname: 'parent_warehouse',
							value: val
						},
						error_handlers: me._pick_list_error_handlers()
					});
				}
			},
				get_query: () => {
					return { filters: { disabled: 0 } };
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
				description: __('You will be asked to choose bay quantities after each scan')
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
				error_handlers: me._pick_list_error_handlers(),
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

		$('#search-item-btn').click(() => this.show_item_search_dialog());

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

	_pick_list_error_handlers() {
		return { DoesNotExistError: () => this._recover_stale_pick_list() };
	}

	_recover_stale_pick_list() {
		if (this._recovering) return;
		this._recovering = true;
		frappe.show_alert({
			message: __('This pick list is no longer available (it may have been reset). Reloading...'),
			indicator: 'orange'
		}, 5);
		this.load_pick_list();
		this._recovering = false;
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
		this.show_bay_breakdown_dialog(item_data);
	}

	_build_bay_rows(item_data) {
		const existing_for_item = this.scanned_items.filter(i => i.item_code === item_data.item_code);
		const bay_map = new Map(item_data.warehouses.map(w => [w.warehouse, { available_qty: w.available_qty, top_level_warehouse: w.top_level_warehouse }]));
		existing_for_item.forEach(r => {
			if (!bay_map.has(r.warehouse)) {
				bay_map.set(r.warehouse, { available_qty: r.available_qty, top_level_warehouse: r.top_level_warehouse || r.warehouse });
			}
		});

		const rows = [...bay_map.entries()].map(([warehouse, info]) => {
			const existing = existing_for_item.find(r => r.warehouse === warehouse);
			return {
				warehouse,
				available_qty: info.available_qty,
				top_level_warehouse: info.top_level_warehouse,
				row_name: existing ? existing.row_name : null,
				qty: existing ? existing.qty : 0
			};
		});
		rows.sort((a, b) => a.warehouse.localeCompare(b.warehouse, undefined, { numeric: true, sensitivity: 'base' }));
		return rows;
	}

	_render_bay_table($wrapper, rows) {
		const render = () => {
			const total = rows.reduce((s, r) => s + r.qty, 0);
			$wrapper.html(`
				<table class="table table-bordered">
					<thead>
						<tr>
							<th style="width:35%">${__('Warehouse')}</th>
							<th style="width:35%">${__('Bay')}</th>
							<th style="width:15%">${__('Available')}</th>
							<th style="width:15%">${__('Qty to Pick')}</th>
						</tr>
					</thead>
					<tbody>
					${rows.map((r, idx) => `
						<tr>
							<td>${r.top_level_warehouse}</td>
							<td>${r.warehouse}</td>
							<td class="text-center">${r.available_qty}</td>
							<td>
								<input type="number"
									class="form-control input-sm bay-qty-input"
									data-idx="${idx}"
									min="0"
									max="${r.available_qty}"
									value="${r.qty}">
							</td>
						</tr>
					`).join('')}
					</tbody>
				</table>
				<div class="text-muted">${__('Total')}: <span class="bay-breakdown-total">${total}</span></div>
			`);
			$wrapper.find('.bay-qty-input').on('change input', function() {
				const idx = $(this).data('idx');
				let val = parseInt($(this).val()) || 0;
				if (val > rows[idx].available_qty) {
					frappe.show_alert({
						message: __('Only {0} available in {1}', [rows[idx].available_qty, rows[idx].warehouse]),
						indicator: 'red'
					}, 4);
					val = rows[idx].qty;
					$(this).val(val);
				}
				rows[idx].qty = val;
				$wrapper.find('.bay-breakdown-total').text(rows.reduce((s, r) => s + r.qty, 0));
			});
		};
		render();
	}

	show_bay_breakdown_dialog(item_data) {
		const me = this;
		const rows = this._build_bay_rows(item_data);

		const dialog = new frappe.ui.Dialog({
			title: __('Bay Breakdown — {0} ({1})', [item_data.item_name, item_data.item_code]),
			size: 'large',
			fields: [{ fieldtype: 'HTML', fieldname: 'breakdown_html' }],
			primary_action_label: __('Save'),
			primary_action: async () => {
				await me._save_bay_breakdown(item_data, rows);
				dialog.hide();
			}
		});
		dialog.on_hide = () => me.focus_barcode_input();

		this._render_bay_table(dialog.fields_dict.breakdown_html.$wrapper, rows);
		dialog.show();
	}

	async _save_bay_breakdown(item_data, rows) {
		for (const r of rows) {
			let result;
			if (r.qty > 0 && !r.row_name) {
				result = await this._add_new_row_async(item_data, r.warehouse, r.available_qty, r.qty, r.top_level_warehouse);
			} else if (r.qty > 0 && r.row_name) {
				result = await this._update_item_qty_async(r, r.qty);
			} else if (r.qty === 0 && r.row_name) {
				result = await this._remove_item_by_row_name_async(r.row_name);
			} else {
				continue;
			}
			if (result && result.ok === false) return;
		}
		this.render_items();
		this.update_submit_button();
		this.play_success_sound();
	}

	_update_item_qty(item, new_qty) {
		frappe.call({
			method: 'ivm.warehouse.services.pick_list.update_pick_list_item_qty',
			args: { pick_list: this.pick_list, row_name: item.row_name, qty: new_qty },
			error_handlers: this._pick_list_error_handlers(),
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

	_add_new_row_async(item_data, warehouse, available_qty, qty, top_level_warehouse) {
		const me = this;
		return new Promise((resolve) => {
			frappe.call({
				method: 'ivm.warehouse.services.pick_list.add_item_to_pick_list',
				args: {
					pick_list: me.pick_list,
					item_code: item_data.item_code,
					warehouse: warehouse,
					qty: qty,
					item_name: item_data.item_name,
					uom: item_data.stock_uom
				},
				error_handlers: {
					DoesNotExistError: () => { me._recover_stale_pick_list(); resolve({ ok: false }); }
				},
				callback: (r) => {
					if (r.message) {
						me.scanned_items.push({
							row_name: r.message.row_name,
							item_code: item_data.item_code,
							item_name: item_data.item_name,
							warehouse: warehouse,
							available_qty: available_qty,
							top_level_warehouse: top_level_warehouse,
							qty: r.message.qty,
							uom: item_data.stock_uom
						});
					}
					resolve({ ok: true });
				}
			});
		});
	}

	_update_item_qty_async(item, new_qty) {
		const me = this;
		return new Promise((resolve) => {
			frappe.call({
				method: 'ivm.warehouse.services.pick_list.update_pick_list_item_qty',
				args: { pick_list: me.pick_list, row_name: item.row_name, qty: new_qty },
				error_handlers: {
					DoesNotExistError: () => { me._recover_stale_pick_list(); resolve({ ok: false }); }
				},
				callback: (r) => {
					if (r.message && r.message.success) {
						const cached = me.scanned_items.find(i => i.row_name === item.row_name);
						if (cached) cached.qty = new_qty;
					}
					resolve({ ok: true });
				}
			});
		});
	}

	_remove_item_by_row_name_async(row_name) {
		const me = this;
		return new Promise((resolve) => {
			frappe.call({
				method: 'ivm.warehouse.services.pick_list.remove_pick_list_item',
				args: { pick_list: me.pick_list, row_name: row_name },
				error_handlers: {
					DoesNotExistError: () => { me._recover_stale_pick_list(); resolve({ ok: false }); }
				},
				callback: (r) => {
					if (r.message && r.message.success) {
						const idx = me.scanned_items.findIndex(i => i.row_name === row_name);
						if (idx !== -1) me.scanned_items.splice(idx, 1);
					}
					resolve({ ok: true });
				}
			});
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
					<td class="text-center">${item.available_qty || 0}</td>
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
			error_handlers: this._pick_list_error_handlers(),
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
					error_handlers: this._pick_list_error_handlers(),
					callback: (r) => {
						if (r.message) {
							frappe.set_route('Form', 'Stock Entry', r.message.stock_entry);
						}
					}
				});
			}
		);
	}

	show_item_search_dialog() {
		const me = this;

		const dialog = new frappe.ui.Dialog({
			title: __('Search Item'),
			size: 'large',
			fields: [{ fieldtype: 'HTML', fieldname: 'content_html' }]
		});

		const $content = dialog.fields_dict.content_html.$wrapper;
		$content.html(`
			<div class="search-filter-row" style="display: flex; gap: 15px; margin-bottom: 15px; flex-wrap: wrap;">
				<div style="flex: 1 1 200px;" id="search-item-name-field"></div>
				<div style="flex: 1 1 200px;" id="search-scope-field"></div>
			</div>
			<div class="search-results-panel"></div>
			<div class="breakdown-panel" style="display: none;"></div>
		`);

		const item_name_field = frappe.ui.form.make_control({
			parent: $content.find('#search-item-name-field'),
			df: {
				fieldtype: 'Data',
				label: __('Item Name'),
				fieldname: 'item_name_search',
				placeholder: __('Type at least 2 characters...')
			},
			render_input: true
		});

		const search_scope_field = frappe.ui.form.make_control({
			parent: $content.find('#search-scope-field'),
			df: {
				fieldtype: 'Link',
				label: __('Search Under'),
				fieldname: 'search_scope',
				options: 'Warehouse',
				onchange: () => {
					const scope = search_scope_field.get_value();
					if (scope) me.last_search_scope = scope;
					me.run_item_search(dialog);
				},
				get_query: () => {
					return { filters: { disabled: 0 } };
				}
			},
			render_input: true
		});
		search_scope_field.set_value(this.last_search_scope);

		dialog.custom_fields = {
			item_name_search: item_name_field,
			search_scope: search_scope_field
		};

		const debounced_search = frappe.utils.debounce(() => me.run_item_search(dialog), 300);
		item_name_field.$input.on('input', debounced_search);

		dialog.on_hide = () => me.focus_barcode_input();

		dialog.show();

		setTimeout(() => {
			item_name_field.$input.focus();
		}, 200);
	}

	run_item_search(dialog) {
		const me = this;
		const txt = (dialog.custom_fields.item_name_search.get_value() || '').trim();
		const scope = dialog.custom_fields.search_scope.get_value() || this.last_search_scope;
		const $results = dialog.fields_dict.content_html.$wrapper.find('.search-results-panel');

		if (txt.length < 2) {
			$results.empty();
			return;
		}

		frappe.call({
			method: 'ivm.warehouse.services.inventory.search_items_by_name',
			args: { txt: txt, parent_warehouse: scope },
			callback: (r) => {
				me.render_search_results(dialog, r.message || []);
			}
		});
	}

	render_search_results(dialog, results) {
		const me = this;
		const $results = dialog.fields_dict.content_html.$wrapper.find('.search-results-panel');

		if (!results.length) {
			$results.html(`<div class="text-muted">${__('No items found with available stock in this scope')}</div>`);
			return;
		}

		$results.html(`
			<table class="table table-bordered">
				<thead>
					<tr>
						<th>${__('Item Code')}</th>
						<th>${__('Item Name')}</th>
						<th style="width:15%">${__('Total Qty')}</th>
						<th style="width:15%">${__('UOM')}</th>
						<th style="width:10%"></th>
					</tr>
				</thead>
				<tbody>
				${results.map((row, idx) => `
					<tr>
						<td>${row.item_code}</td>
						<td>${row.item_name}</td>
						<td class="text-center">${row.total_qty}</td>
						<td>${row.stock_uom}</td>
						<td class="text-center">
							<button class="btn btn-xs btn-primary search-result-select" data-idx="${idx}">${__('Select')}</button>
						</td>
					</tr>
				`).join('')}
				</tbody>
			</table>
		`);

		$results.find('.search-result-select').on('click', function() {
			const idx = $(this).data('idx');
			const row = results[idx];
			const scope = dialog.custom_fields.search_scope.get_value() || me.last_search_scope;
			me.select_search_result(dialog, row.item_code, scope);
		});
	}

	select_search_result(dialog, item_code, scope) {
		const me = this;
		frappe.call({
			method: 'ivm.warehouse.services.inventory.get_item_with_warehouse',
			args: { item_code: item_code, parent_warehouse: scope },
			callback: (r) => {
				if (!r.message || !r.message.warehouses || r.message.warehouses.length === 0) {
					frappe.show_alert({ message: __('No stock found for this item in the selected scope'), indicator: 'orange' }, 5);
					return;
				}
				me.show_breakdown_panel(dialog, r.message);
			}
		});
	}

	show_breakdown_panel(dialog, item_data) {
		const me = this;
		const rows = this._build_bay_rows(item_data);

		dialog.fields_dict.content_html.$wrapper.find('.search-filter-row').hide();

		const $content = dialog.fields_dict.content_html.$wrapper;
		const $searchPanel = $content.find('.search-results-panel');
		const $panel = $content.find('.breakdown-panel');

		$searchPanel.hide();
		$panel.show().html(`
			<div style="margin-bottom: 10px;">
				<a href="#" class="search-back-link">&larr; ${__('Back to search')}</a>
			</div>
			<h5>${item_data.item_name} (${item_data.item_code})</h5>
			<div class="breakdown-table-container"></div>
			<button class="btn btn-primary search-add-btn" style="margin-top: 15px;">${__('Add to Pick List')}</button>
		`);

		this._render_bay_table($panel.find('.breakdown-table-container'), rows);

		$panel.find('.search-back-link').on('click', (e) => {
			e.preventDefault();
			me.show_search_panel(dialog);
		});

		$panel.find('.search-add-btn').on('click', async () => {
			await me._save_bay_breakdown(item_data, rows);
			me.show_search_panel(dialog);
		});
	}

	show_search_panel(dialog) {
		const $content = dialog.fields_dict.content_html.$wrapper;
		$content.find('.breakdown-panel').hide();
		$content.find('.search-results-panel').show();
		$content.find('.search-filter-row').show();
	}

	play_success_sound() {}
	play_error_sound() {}
}

frappe.pages['item_scanner'].on_page_show = function(wrapper) {
	const page = wrapper.page;

	// Capture the warehouse request from route_options (set by frappe.set_route)
	// or from the URL query string. route_options is consumed after read, so grab
	// it here before anything else clears it.
	const new_wr = (frappe.route_options && frappe.route_options.warehouse_request)
		|| frappe.urllib.get_arg('warehouse_request');

	// Clear route_options so Frappe doesn't try to consume them elsewhere
	if (frappe.route_options) {
		delete frappe.route_options.warehouse_request;
	}

	// Reinitialize if the warehouse request changed or on first visit
	if (!page.item_scanner || (new_wr && page.item_scanner.warehouse_request !== new_wr)) {
		page.item_scanner = new ItemScanner(page, new_wr);
	} else if (!page.item_scanner.pick_list_submitted) {
		page.item_scanner.load_pick_list();
	}
	cur_page.item_scanner = page.item_scanner;
};
