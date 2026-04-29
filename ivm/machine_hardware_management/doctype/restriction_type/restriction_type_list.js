frappe.listview_settings['Restriction Type'] = {
    refresh: function(listview) {
        listview.page.add_inner_button("Sync", function() {
            frappe.call({
                method: "ivm.machine_hardware_management.doctype.restriction_type.restriction_type.sync",
                callback: function(r) {
                    frappe.msgprint(r.message || "Sync complete");
                }
            });
        });
    },
};