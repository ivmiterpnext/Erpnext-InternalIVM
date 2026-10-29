// __user placeholder support for sidebar filters.
// Frappe core now natively converts item.filters into route_options correctly (the old
// array-encoding bug this file used to work around is fixed upstream). This patch only
// substitutes __user with the current session user before core's own get_route() runs —
// it no longer touches get_path/make or blanks out filters.
//
// Example: a filter value of _assign like "%__user%" resolves to the current logged-in user.
(function () {
	if (!frappe.ui?.sidebar_item) return;
	if (frappe.ui.sidebar_item._ivm_user_filter_patched) return;
	frappe.ui.sidebar_item._ivm_user_filter_patched = true;

	const _orig_get_route = frappe.ui.sidebar_item.get_route;
	frappe.ui.sidebar_item.get_route = function (item, edit_mode = false, shell = null) {
		if (item?.filters && typeof item.filters === "string" && item.filters.includes("__user")) {
			item = { ...item, filters: item.filters.replace(/__user/g, frappe.session.user) };
		}
		return _orig_get_route.call(this, item, edit_mode, shell);
	};
})();
