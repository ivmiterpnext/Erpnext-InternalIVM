frappe.listview_settings['Machine Authorization Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "ivm.machine_hardware_management.doctype.machine_authorization_type.machine_authorization_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};