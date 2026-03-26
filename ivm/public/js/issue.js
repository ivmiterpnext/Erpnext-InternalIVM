frappe.ui.form.on('Issue', {
    refresh: function(frm) {
        // Lock subject and issue_type after save
        if (!frm.doc.__islocal) {
            frm.set_df_property('subject', 'read_only', 1);
            frm.set_df_property('issue_type', 'read_only', 1);
        }

        // Initialize embedded form if not exists
        if (!frm.embedded_ticket_form) {
            frm.embedded_ticket_form = new ivm.EmbeddedForm({
                parent_form: frm,
                html_field_name: 'custom_sub_ticket_form',
                embedded_doctype_field: 'sub_ticket_type',
                dynamic_link_field: 'sub_ticket',
                save_method: 'ivm.ivm_support.services.ticket_manager.save_sub_ticket'
            });
        }

        // Render sub-ticket form if ticket exists
        if (frm.embedded_ticket_form.should_render()) {
            frm.embedded_ticket_form.render();
        }
    },

    after_save: function(frm) {
        frm.set_df_property('subject', 'read_only', 1);
        frm.set_df_property('issue_type', 'read_only', 1);

        if (frm.embedded_ticket_form && frm.embedded_ticket_form.should_render()) {
            frm.embedded_ticket_form.render();
        }
    },

    before_save: function(frm) {
        // Save sub-ticket fields before saving Issue
        if (frm.embedded_ticket_form && frm.embedded_ticket_form.is_dirty) {
            return frm.embedded_ticket_form.save();
        }
    },

    issue_type: function(frm) {
        // Re-render if ticket already exists
        if (frm.embedded_ticket_form && frm.embedded_ticket_form.should_render()) {
            frm.embedded_ticket_form.render();
        }
    },

    sub_ticket_type: function(frm) {
        // Clear sub_ticket when ticket type changes to prevent stale data
        if (frm.doc.sub_ticket) {
            frm.set_value('sub_ticket', '');
            
            // Clear the old form from DOM
            if (frm.embedded_ticket_form) {
                frm.embedded_ticket_form.clear();
            }
        }
    }
});
