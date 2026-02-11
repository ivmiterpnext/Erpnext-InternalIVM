frappe.listview_settings['Restriction Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "mssql_frappe.mssql_frappe.doctype.restriction_type.restriction_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};