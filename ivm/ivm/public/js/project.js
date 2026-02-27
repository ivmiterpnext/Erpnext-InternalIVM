frappe.ui.form.on('Project', {
    status: function(frm) {
        if (frm.doc.status === 'Ready to Ship') {
            if (!frm.doc.contacts_completed_date || !frm.doc.delivery_contact) {
                frappe.msgprint(__('Please fill in both Contacts Completed Date and Delivery Contact before moving to Ready to Ship.'));
                frm.set_value('status', frm.doc.__unsaved_status || '');
            }
        }
    },
    
    before_save: function(frm) {
        if (frm.doc.status === 'Ready to Ship') {
            if (!frm.doc.contacts_completed_date || !frm.doc.delivery_contact) {
                frappe.throw(__('Please fill in both Contacts Completed Date and Delivery Contact before saving.'));
            }
        }
    }
});