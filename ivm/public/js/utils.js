// TEMPORARY: Persist active sidebar across refreshes until Frappe fixes natively
// Remove patch_sidebar_prototype when upstream fix lands in frappe/frappe
//
// If Workspace Sidebar item filters need to be edited, two frappe core files
// must be temporarily patched on dev before editing, then reverted after export:
//
// 1. apps/frappe/frappe/public/js/frappe/form/controls/dynamic_link.js line 12
//    Change: options = cur_list.page.fields_dict[this.df.options].get_input_value();
//    To:     options = cur_list.page.fields_dict[this.df.options]?.get_input_value() ?? "";
//
// 2. apps/frappe/frappe/public/js/frappe/ui/sidebar/sidebar_editor.js ~line 436
//    Change: me.filter_group.get_filters();
//    To:     values.filters = JSON.stringify(me.filter_group.get_filters());
//
// After patching run: bench build --app frappe
// After editing filters, export fixtures: bench --site site1.local export-fixtures
// Filters persist via migration — live instances do not need the JS patches.
(function () {
	const KEY = "ivm_preferred_sidebar";

	function patch_sidebar_prototype() {
		if (!frappe.ui?.Sidebar?.prototype) return;
		if (frappe.ui.Sidebar.prototype._ivm_patched) return;
		frappe.ui.Sidebar.prototype._ivm_patched = true;

		const _orig_set_ws = frappe.ui.Sidebar.prototype.set_workspace_sidebar;
		frappe.ui.Sidebar.prototype.set_workspace_sidebar = function (...args) {
			const saved = localStorage.getItem(KEY);
			const is_fresh_load = !this.workspace_sidebar_items?.length;

			if (saved && is_fresh_load) {
				// On page load/refresh, setup() hasn't run yet — call it directly
				// but only if the saved sidebar is actually valid for this route
				const route = frappe.get_route();
				const entity_name = route?.[1] || route?.[0];
				const valid_sidebars = entity_name ? this.get_workspace_sidebars(entity_name) : [];
				if (valid_sidebars.includes(saved)) {
					this.setup(saved);
					return;
				}
			} else if (saved && !is_fresh_load) {
				// Mid-session navigation: hint the title so the "keep current" check passes
				this.sidebar_title = saved;
			}

			return _orig_set_ws.apply(this, args);
		};

		const _orig_setup = frappe.ui.Sidebar.prototype.setup;
		frappe.ui.Sidebar.prototype.setup = function (workspace_title, ...args) {
			localStorage.setItem(KEY, workspace_title);
			return _orig_setup.call(this, workspace_title);
		};
	}

	patch_sidebar_prototype();
	frappe.after_ajax(patch_sidebar_prototype);
})();
// END TEMPORARY

// Sidebar item filter fix + __user placeholder support.
//
// Frappe bug: get_path() puts DocType list filters into args.route_options which
// generate_route() URL-encodes as query params, turning arrays like ["like","%val%"]
// into the string "like,%val%". The list view then treats it as a literal equals.
// Fix: capture filters at render time, set frappe.route_options only on click.
//
// __user placeholder: use __user in any filter value to reference the current
// logged-in user at navigation time. Example: _assign like "%__user%"
frappe.after_ajax(function () {
	if (!frappe.ui?.sidebar_item?.TypeLink?.prototype) return;
	if (frappe.ui.sidebar_item.TypeLink.prototype._ivm_user_filter_patched) return;
	frappe.ui.sidebar_item.TypeLink.prototype._ivm_user_filter_patched = true;

	const _orig_get_path = frappe.ui.sidebar_item.TypeLink.prototype.get_path;
	frappe.ui.sidebar_item.TypeLink.prototype.get_path = function () {
		if (this.item.filters && this.item.link_type === "DocType") {
			let filters = this.item.filters.replace(/__user/g, frappe.session.user);
			// Store resolved filters for the click handler — don't set route_options here
			// as get_path() is called during render for every item, not just the clicked one
			this._ivm_route_filters = JSON.parse(
				frappe.utils.get_filter_as_json(JSON.parse(filters))
			);
			// Strip filters so generate_route doesn't URL-encode them into query params
			const orig_filters = this.item.filters;
			this.item = { ...this.item, filters: null };
			const path = _orig_get_path.call(this);
			this.item = { ...this.item, filters: orig_filters };
			return path;
		}
		return _orig_get_path.call(this);
	};

	const _orig_make = frappe.ui.sidebar_item.TypeLink.prototype.make;
	frappe.ui.sidebar_item.TypeLink.prototype.make = function () {
		_orig_make.call(this);
		if (this._ivm_route_filters && this.wrapper) {
			const filters = this._ivm_route_filters;
			const wrapper = this.wrapper;
			this.wrapper.on("click.ivm_filters", function () {
				frappe.route_options = filters;
				// Correct active highlight after routing settles — same URL path means
				// is_route_in_sidebar matches all filtered items and last one wins
				setTimeout(() => {
					$(".active-sidebar").removeClass("active-sidebar");
					wrapper.addClass("active-sidebar");
					frappe.app.sidebar.active_item = wrapper;
				}, 50);
			});
		}
	};
});
