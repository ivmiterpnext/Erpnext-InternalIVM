// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Valuation Analytics"] = {
	filters: [
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			default: "",
			get_query: () => ({ filters: { is_stock_item: 1 } }),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			default: "",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.defaults.get_global_default("year_start_date"),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.defaults.get_global_default("year_end_date"),
			reqd: 1,
		},
		{
			fieldname: "range",
			label: __("Range"),
			fieldtype: "Select",
			options: [
				{ value: "Weekly", label: __("Weekly") },
				{ value: "Monthly", label: __("Monthly") },
				{ value: "Quarterly", label: __("Quarterly") },
				{ value: "Yearly", label: __("Yearly") },
			],
			default: "Monthly",
			reqd: 1,
		},
		{
			fieldname: "hide_zero_qty_items",
			label: __("Hide Zero Qty Items"),
			fieldtype: "Check",
			default: 0,
		},
	],

	after_datatable_render(datatable) {
		if (
			datatable.bodyRenderer &&
			typeof datatable.bodyRenderer.renderFooter === "function" &&
			!datatable.bodyRenderer.__ivm_disable_total_patched
		) {
			const original_render_footer = datatable.bodyRenderer.renderFooter.bind(datatable.bodyRenderer);
			datatable.bodyRenderer.renderFooter = function () {
				original_render_footer();
				datatable.datamanager
					.getColumns()
					.filter((column) => column.disable_total)
					.forEach((column) => {
						const content_el = datatable.footer.querySelector(
							`.dt-cell--col-${column.colIndex} .dt-cell__content`
						);
						if (content_el) {
							content_el.textContent = "";
						}
					});
			};
			datatable.bodyRenderer.__ivm_disable_total_patched = true;
		}
		datatable.bodyRenderer.renderFooter();
	},
};
