frappe.listview_settings['Machine Contract Length Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "ivm.machine_hardware_management.doctype.machine_contract_length_type.machine_contract_length_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};