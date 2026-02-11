frappe.listview_settings['Board Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "mssql_frappe.mssql_frappe.doctype.board_type.board_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};