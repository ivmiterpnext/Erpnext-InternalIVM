frappe.ui.form.on('Deployment Location', {
    after_save: async function (frm) {
        if (frm.doc.opportunity) {
            frappe.call({
                method: 'ivm.api.deployment_location_equipments',
                args: {
                    opportunity : frm.doc.opportunity, // Filter by the name of the Opportunity document
                    machines : frm.doc.machines_at_location,
                    lockers :frm.doc.total_lockers_at_location // Specify the field you want to retrieve
                }
            });
        }
    }
});