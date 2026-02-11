frappe.listview_settings['Fee Rate'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "machine_hardware_management.machine_hardware_management.doctype.fee_rate.fee_rate.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};