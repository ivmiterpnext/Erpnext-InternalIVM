frappe.ui.form.on('Issue', {
    refresh: function(frm) {
        // Lock issue_type after save
        if (!frm.doc.__islocal) {
            frm.set_df_property('issue_type', 'read_only', 1);
        }
        
        // Render sub-ticket form if ticket exists
        if (frm.doc.sub_ticket && frm.doc.sub_ticket_type) {
            render_sub_ticket_form(frm);
        }
    },
    
    after_save: function(frm) {
        frm.set_df_property('issue_type', 'read_only', 1);
        
        if (frm.doc.sub_ticket && frm.doc.sub_ticket_type) {
            render_sub_ticket_form(frm);
        }
    },
    
    before_save: function(frm) {
        // Save sub-ticket fields before saving Issue
        if (frm.doc.sub_ticket && frm._sub_ticket_field_controls) {
            return save_sub_ticket_before_issue_save(frm);
        }
    },
    
    issue_type: function(frm) {
        // Re-render if ticket already exists
        if (frm.doc.sub_ticket && frm.doc.sub_ticket_type) {
            render_sub_ticket_form(frm);
        }
    }
});

function save_sub_ticket_before_issue_save(frm) {
    // Only save if there were actual changes
    if (!frm._sub_ticket_dirty) {
        return;
    }
    
    const field_values = {};
    const controls = frm._sub_ticket_field_controls;
    
    for (let fieldname in controls) {
        field_values[fieldname] = controls[fieldname].get_value();
    }
    
    // Save synchronously with dynamic doctype
    return frappe.call({
        method: 'ivm.ivm_support.services.ticket_manager.save_sub_ticket',
        args: {
            ticket_doctype: frm.doc.sub_ticket_type,  // Dynamic doctype
            ticket_name: frm.doc.sub_ticket,
            field_values: field_values
        },
        async: false,
        callback: function(r) {
            if (!r.exc) {
                frm._sub_ticket_dirty = false;
            }
        }
    });
}

function render_sub_ticket_form(frm) {
    const wrapper = frm.fields_dict['custom_sub_ticket_form'].$wrapper;
    wrapper.empty();
    
    if (!frm.doc.sub_ticket || !frm.doc.sub_ticket_type) {
        return;
    }
    
    // Load the ticket document (dynamically based on sub_ticket_type)
    frappe.model.with_doc(frm.doc.sub_ticket_type, frm.doc.sub_ticket, function() {
        const ticket_doc = frappe.get_doc(frm.doc.sub_ticket_type, frm.doc.sub_ticket);
        
        frappe.model.with_doctype(frm.doc.sub_ticket_type, function() {
            const meta = frappe.get_meta(frm.doc.sub_ticket_type);
            const form_container = $('<div class="embedded-form"></div>').appendTo(wrapper);
            form_container.append(`<h4 style="margin-bottom: 15px; color: #1f2937;">${ticket_type_label} Details</h4>`);
            
            const field_controls = {};
            let current_section = null;
            
            meta.fields.forEach(function(df) {
                // Skip the 'issue' link field and hidden fields
                if (df.fieldname === 'issue' || df.hidden) return;
                
                // Handle Section Breaks
                if (df.fieldtype === 'Section Break') {
                    if (df.label) {
                        current_section = $(`<div class="form-section">
                            <div class="section-head">${df.label}</div>
                        </div>`).appendTo(form_container);
                    }
                    return;
                }
                
                // Handle Column Breaks
                if (df.fieldtype === 'Column Break') {
                    return;
                }
                
                const field_wrapper = $('<div class="frappe-control"></div>');
                
                if (current_section) {
                    field_wrapper.appendTo(current_section);
                } else {
                    field_wrapper.appendTo(form_container);
                }
                
                const field = frappe.ui.form.make_control({
                    df: df,
                    parent: field_wrapper,
                    only_input: false
                });
                
                field.set_value(ticket_doc[df.fieldname]);
                field.refresh();
                
                field_controls[df.fieldname] = field;
                
                // Mark Issue as dirty when any ticket field changes
                if (field.$input) {
                    field.$input.on('change', function() {
                        frm._sub_ticket_dirty = true;
                        frm.dirty();
                    });
                }
                
                // Also handle link fields and other input types
                if (field.$wrapper) {
                    field.$wrapper.on('change', 'input, select, textarea', function() {
                        frm._sub_ticket_dirty = true;
                        frm.dirty();
                    });
                }
            });
            
            // Store controls for save handler
            frm._sub_ticket_field_controls = field_controls;
            frm._sub_ticket_dirty = false;
        });
    });
}