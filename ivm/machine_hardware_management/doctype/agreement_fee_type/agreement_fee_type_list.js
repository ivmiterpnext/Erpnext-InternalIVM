frappe.listview_settings['Agreement Fee Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "machine_hardware_management.machine_hardware_management.doctype.agreement_fee_type.agreement_fee_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};