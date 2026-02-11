frappe.listview_settings['Machine Activity Log Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "ivm.machine_hardware_management.doctype.machine_activity_log_type.machine_activity_log_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};