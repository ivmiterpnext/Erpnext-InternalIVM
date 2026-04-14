frappe.pages['ivm_desktop'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'IVM Dashboard',
		single_column: true
	});

	page.main.html(frappe.render_template('ivm_desktop'));

	page.set_secondary_action('Refresh', () => {
		wrapper.desktop.refresh();
	}, 'refresh-cw');

	wrapper.desktop = new IVMDesktop(page);
};

frappe.pages['ivm_desktop'].on_page_show = function(wrapper) {
	if (wrapper.desktop) {
		wrapper.desktop.refresh();
	}
};

class IVMDesktop {
	constructor(page) {
		this.page = page;
		this.$container = $(page.main).find('.ivm-desktop');
		this._card_actions = [];
		this.refresh();
	}

	refresh() {
		frappe.call({
			method: 'ivm.api.get_desktop_data',
			callback: (r) => {
				if (r.message) {
					this.data = r.message;
					this.roles = this.data.roles || [];
					this.render();
				}
			}
		});
	}

	has_role(roles) {
		if (this.roles.includes('Administrator') || this.roles.includes('System Manager')) {
			return true;
		}
		return roles.some(r => this.roles.includes(r));
	}

	navigate(doctype, filters) {
		if (filters) {
			frappe.route_options = filters;
		}
		frappe.set_route('List', doctype);
	}

	get_sections() {
		const user = frappe.session.user;
		return [
			{
				id: 'tickets',
				title: 'Tickets',
				color: '#2490EF',
				roles: ['Support Team', 'Workspace Manager'],
				create_doctype: 'Issue',
				cards: [
					{
						label: 'New Support',
						sublabel: 'Tickets',
						count: this.data.new_support_tickets,
						filters: { issue_type: 'Support', status: 'New' },
						doctype: 'Issue'
					},
					{
						label: 'Assigned',
						sublabel: 'to Me',
						count: this.data.my_tickets,
						filters: { _assign: ['like', '%"' + user + '"%'] },
						doctype: 'Issue'
					},
					{
						label: 'New IT',
						sublabel: 'Tickets',
						count: this.data.new_it_tickets,
						filters: { issue_type: 'IT', status: 'New' },
						doctype: 'Issue'
					},
					{
						label: 'All Open',
						sublabel: 'Tickets',
						count: this.data.open_tickets_total,
						filters: { status: ['not in', ['Closed', 'Resolved']] },
						doctype: 'Issue'
					}
				],
				links: [
					{ label: 'All Tickets', url: '/app/issue' },
					{ label: 'Cases Report', url: '/app/query-report/Cases' }
				]
			},
			{
				id: 'deployments',
				title: 'Deployments',
				color: '#38A169',
				roles: ['Projects User', 'Workspace Manager'],
				create_doctype: 'Project',
				cards: [
					{
						label: 'Active',
						sublabel: 'Deployments',
						count: this.data.active_deployments,
						filters: { project_type: 'Deployment', status: 'Open' },
						doctype: 'Project'
					},
					{
						label: 'My',
						sublabel: 'Deployments',
						count: this.data.my_deployments,
						filters: { project_type: 'Deployment', _assign: ['like', '%"' + user + '"%'] },
						doctype: 'Project'
					}
				],
				links: [
					{ label: 'All Projects', url: '/app/project' },
					{ label: 'Active Deployments Report', url: '/app/query-report/Active Deployments' }
				]
			},
			{
				id: 'warehouse',
				title: 'Warehouse Requests',
				color: '#DD6B20',
				roles: ['Stock User', 'Workspace Manager'],
				create_doctype: 'Warehouse Request',
				cards: [
					{
						label: 'Open',
						sublabel: 'Requests',
						count: this.data.open_warehouse_requests,
						filters: { docstatus: 0 },
						doctype: 'Warehouse Request'
					}
				],
				links: [
					{ label: 'All Requests', url: '/app/warehouse-request' },
					{ label: 'Item Scanner', url: '/app/item_scanner' }
				]
			},
			{
				id: 'stock',
				title: 'Stock',
				color: '#805AD5',
				roles: ['Stock User', 'Workspace Manager'],
				cards: [],
				links: [
					{ label: 'Stock Entry', url: '/app/stock-entry' },
					{ label: 'Delivery Note', url: '/app/delivery-note' },
					{ label: 'Items', url: '/app/item' },
					{ label: 'Stock Ledger', url: '/app/query-report/Stock Ledger' }
				]
			},
			{
				id: 'crm',
				title: 'CRM',
				color: '#319795',
				roles: ['Sales User', 'Sales Manager', 'Workspace Manager'],
				cards: [
					{
						label: 'Open',
						sublabel: 'Leads',
						count: this.data.open_leads,
						filters: { status: ['not in', ['Converted', 'Do Not Contact']] },
						doctype: 'Lead'
					},
					{
						label: 'Open',
						sublabel: 'Opportunities',
						count: this.data.open_opportunities,
						filters: { status: 'Open' },
						doctype: 'Opportunity'
					}
				],
				links: [
					{ label: 'Leads', url: '/app/lead' },
					{ label: 'Opportunities', url: '/app/opportunity' },
					{ label: 'Customers', url: '/app/customer' },
					{ label: 'Sales Forecast', url: '/app/query-report/Monthly Sales Forecast' }
				]
			},
			{
				id: 'custom-issues',
				title: 'Custom Issues',
				color: '#E53E3E',
				roles: ['Support Team', 'Workspace Manager'],
				cards: [
					{
						label: 'Accounts',
						sublabel: 'Receivable',
						count: this.data.ar_issues,
						filters: { issue_type: 'Receivable', status: ['not in', ['Closed', 'Resolved']] },
						doctype: 'Issue'
					},
					{
						label: 'Vending',
						sublabel: 'Management',
						count: this.data.vending_issues,
						filters: { issue_type: 'Vending Management', status: ['not in', ['Closed', 'Resolved']] },
						doctype: 'Issue'
					}
				],
				links: [
					{ label: 'Accounts Audit Report', url: '/app/query-report/Accounts Audit' }
				]
			}
		];
	}

	render() {
		this._card_actions = [];

		let html = this.render_kpi_bar();
		html += '<div class="ivm-sections-grid">';

		this.get_sections().forEach(section => {
			if (this.has_role(section.roles)) {
				html += this.render_section(section);
			}
		});

		html += '</div>';

		this.$container.html(html);
		this.bind_events();
	}

	render_kpi_bar() {
		const kpis = [
			{
				label: 'Open Tickets',
				value: this.data.open_tickets_total,
				color: '#2490EF',
				doctype: 'Issue',
				filters: { status: ['not in', ['Closed', 'Resolved']] }
			},
			{
				label: 'Active Deployments',
				value: this.data.active_deployments,
				color: '#38A169',
				doctype: 'Project',
				filters: { project_type: 'Deployment', status: 'Open' }
			},
			{
				label: 'Open WR',
				value: this.data.open_warehouse_requests,
				color: '#DD6B20',
				doctype: 'Warehouse Request',
				filters: { docstatus: 0 }
			},
			{
				label: 'Opportunities',
				value: this.data.open_opportunities,
				color: '#319795',
				doctype: 'Opportunity',
				filters: { status: 'Open' }
			}
		];

		let html = '<div class="ivm-kpi-bar">';
		kpis.forEach(kpi => {
			const actionIdx = this._card_actions.length;
			this._card_actions.push({ doctype: kpi.doctype, filters: kpi.filters });
			html += `
				<div class="ivm-kpi-card" data-action="${actionIdx}">
					<div class="ivm-kpi-value" style="color: ${kpi.color}">${kpi.value}</div>
					<div class="ivm-kpi-label">${kpi.label}</div>
				</div>
			`;
		});
		html += '</div>';
		return html;
	}

	render_section(config) {
		let body_html = '';

		if (config.cards && config.cards.length) {
			body_html += '<div class="ivm-cards-grid">';
			config.cards.forEach(card => {
				const actionIdx = this._card_actions.length;
				this._card_actions.push({ doctype: card.doctype, filters: card.filters });
				body_html += `
					<div class="ivm-metric-card" data-action="${actionIdx}">
						<div class="ivm-metric-count" style="color: ${config.color}">${card.count}</div>
						<div class="ivm-metric-label">${card.label}</div>
						${card.sublabel ? '<div class="ivm-metric-sublabel">' + card.sublabel + '</div>' : ''}
					</div>
				`;
			});
			body_html += '</div>';
		}

		if (config.links && config.links.length) {
			body_html += '<div class="ivm-section-links">';
			config.links.forEach(link => {
				body_html += '<a href="' + link.url + '" class="ivm-section-link">' + link.label + ' &rsaquo;</a>';
			});
			body_html += '</div>';
		}

		let create_btn = '';
		if (config.create_doctype) {
			create_btn = '<button class="btn btn-xs btn-default ivm-create-btn" data-doctype="' + config.create_doctype + '">+ New</button>';
		}

		return `
			<div class="ivm-section" id="ivm-section-${config.id}">
				<div class="ivm-section-header" style="border-left-color: ${config.color}">
					<h4 class="ivm-section-title">${config.title}</h4>
					${create_btn}
				</div>
				<div class="ivm-section-body">
					${body_html}
				</div>
			</div>
		`;
	}

	bind_events() {
		this.$container.find('.ivm-metric-card, .ivm-kpi-card').on('click', (e) => {
			const actionIdx = $(e.currentTarget).data('action');
			const action = this._card_actions[actionIdx];
			if (action) {
				this.navigate(action.doctype, action.filters);
			}
		});

		this.$container.find('.ivm-create-btn').on('click', (e) => {
			e.stopPropagation();
			const doctype = $(e.currentTarget).data('doctype');
			frappe.new_doc(doctype);
		});
	}
}
