// Copyright (c) 2025, Dev and contributors
// For license information, please see license.txt

frappe.listview_settings['Smart Screen Configuration'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "mssql_frappe.mssql_frappe.doctype.smart_screen_configuration.smart_screen_configuration.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};