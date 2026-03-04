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
    },

    custom_generate_smartstation_build_requests: function(frm) {
        if (!frm.doc.planogram_approved_date || !frm.doc.custom_planogram_approved_by || !frm.doc.custom_label_file_created) {
            frappe.msgprint(__('Planogram must be approved and Label File must be created before generating SmartStation Build requests.'));
            return;
        }
        // TODO: Add logic for generating SmartStation Build Requests here
        frappe.msgprint(__('SmartStation Build Requests logic not yet implemented.'));
    },

    custom_generate_smartsync_build_requests: function(frm) {
        if (!frm.doc.locker_configuration_approved_date || !frm.doc.custom_locker_configuration_approved_by) {
            frappe.msgprint(__('Locker Configuration must be approved before generating SmartSync Build requests.'));
            return;
        }
        // TODO: Add logic for generating SmartSync Build Requests here
        frappe.msgprint(__('SmartSync Build Requests logic not yet implemented.'));
    },

    custom_generate_smartlocker_build_requests: function(frm) {
        if (!frm.doc.locker_configuration_approved_date || !frm.doc.custom_locker_configuration_approved_by) {
            frappe.msgprint(__('Locker Configuration must be approved before generating SmartLocker Build requests.'));
            return;
        }
        // TODO: Add logic for generating SmartLocker Build Requests here
        frappe.msgprint(__('SmartLocker Build Requests logic not yet implemented.'));
    },

    custom_generate_smartvault_build_requests: function(frm) {
        if (!frm.doc.vault_configuration_approved_date || !frm.doc.custom_vault_configuration_approved_by) {
            frappe.msgprint(__('Vault Configuration must be approved before generating SmartVault Build requests.'));
            return;
        }
        // TODO: Add logic for generating SmartVault Build Requests here
        frappe.msgprint(__('SmartVault Build Requests logic not yet implemented.'));
    },

    custom_generate_smartcenter_build_requests: function(frm) {
        if (!frm.doc.kiosk_configuration_approved_date || !frm.doc.custom_kiosk_configuration_approved_by) {
            frappe.msgprint(__('Kiosk Configuration must be approved before generating SmartCenter Build requests.'));
            return;
        }
        // TODO: Add logic for generating SmartCenter Build Requests here
        frappe.msgprint(__('SmartCenter Build Requests logic not yet implemented.'));
    },

    // When Wrap Approved (Either by Approved Date or some other way), Generate Wrap Request.
});