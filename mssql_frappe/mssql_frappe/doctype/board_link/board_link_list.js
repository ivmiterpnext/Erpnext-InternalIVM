frappe.listview_settings['Board Link'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "mssql_frappe.mssql_frappe.doctype.board_link.board_link.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};