frappe.listview_settings['Board Connection'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "machine_hardware_management.machine_hardware_management.doctype.board_connection.board_connection.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};