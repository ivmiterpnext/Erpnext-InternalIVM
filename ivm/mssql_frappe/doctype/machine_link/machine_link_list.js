frappe.listview_settings['Machine Link'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "mssql_frappe.mssql_frappe.doctype.machine_link.machine_link.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};