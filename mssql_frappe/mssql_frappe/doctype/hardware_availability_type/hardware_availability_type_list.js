frappe.listview_settings['Hardware Availability Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "mssql_frappe.mssql_frappe.doctype.hardware_availability_type.hardware_availability_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};