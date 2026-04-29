frappe.listview_settings['Hardware Connectivity Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "ivm.machine_hardware_management.doctype.hardware_connectivity_type.hardware_connectivity_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};