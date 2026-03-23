frappe.ui.form.on('Issue', {
    refresh: function(frm) {
        // Lock subject and issue_type after save
        if (!frm.doc.__islocal) {
        frm.set_df_property('subject', 'read_only', 1);
        frm.set_df_property('issue_type', 'read_only', 1);
        }

        // Render sub-ticket form if ticket exists
        if (frm.doc.sub_ticket && frm.doc.sub_ticket_type) {
            render_sub_ticket_form(frm);
        }
    },

    after_save: function(frm) {
        frm.set_df_property('subject', 'read_only', 1);
        frm.set_df_property('issue_type', 'read_only', 1);

        if (frm.doc.sub_ticket && frm.doc.sub_ticket_type) {
            render_sub_ticket_form(frm);
        }
    },

    before_save: function(frm) {
        // Save sub-ticket fields before saving Issue
        if (frm.doc.sub_ticket && frm._sub_ticket_field_controls) {
            return save_sub_ticket(frm);
        }
    },

    issue_type: function(frm) {
        // Re-render if ticket already exists
        if (frm.doc.sub_ticket && frm.doc.sub_ticket_type) {
            render_sub_ticket_form(frm);
        }
    },

    sub_ticket_type: function(frm) {
        // Clear sub_ticket when ticket type changes to prevent stale data
        if (frm.doc.sub_ticket) {
            frm.set_value('sub_ticket', '');
            frm._sub_ticket_field_controls = null;
            frm._sub_ticket_dirty = false;
            
            // Clear the old form from DOM
            render_sub_ticket_form(frm);
        }
    }
});

function render_sub_ticket_form(frm) {
    const wrapper = frm.fields_dict['custom_sub_ticket_form'].$wrapper;

    // Clear wrapper and find the embedded form that was moved outside
    wrapper.empty();
    const parent_section = wrapper.closest('.form-section');
    if (parent_section.length) {
        // Remove embedded form that's a sibling of parent_section (moved there previously)
        parent_section.nextAll('.embedded-form').remove();
    }

    if (!frm.doc.sub_ticket || !frm.doc.sub_ticket_type) {
        return;
    }

    // Load the sub-ticket doc based on sub_ticket_type
    frappe.model.with_doc(frm.doc.sub_ticket_type, frm.doc.sub_ticket, function() {
        const ticket_doc = frappe.get_doc(frm.doc.sub_ticket_type, frm.doc.sub_ticket);

        frappe.model.with_doctype(frm.doc.sub_ticket_type, function() {
            const meta = frappe.get_meta(frm.doc.sub_ticket_type);
            const form_container = $('<div class="embedded-form"></div>').appendTo(wrapper);

            // Move embedded form out of section-body but keep inside parent form-section for styling purposes
            const parent_body = wrapper.closest('.section-body');
            const parent_section = wrapper.closest('.form-section');
            if (parent_body.length && parent_section.length) {
                form_container.detach();
                parent_section.after(form_container);
                parent_section.hide();                parent_section.addClass('embedded-form-parent');            }

            const field_controls = {};
            const state = {
                current_section: null,
                current_row: null,
                current_column: null,
                skip_current_section: false
            };

            meta.fields.forEach(function(df) {
                if (df.fieldtype === 'Tab Break') {
                    handle_tab_break(df, ticket_doc, form_container, state);
                    return;
                }

                if (df.fieldtype === 'Section Break') {
                    handle_section_break(df, ticket_doc, form_container, state);
                    return;
                }

                if (df.hidden) return;

                if (df.fieldtype === 'Column Break') {
                    handle_column_break(state);
                    return;
                }
                
                // Skip all fields if in a hidden section
                if (state.skip_current_section) {
                    debug_log('Skipping field', df.fieldname, '(in hidden section)');
                    return;
                }
                
                // Evaluate field/section's depends_on
                if (df.depends_on) {
                    debug_log('Evaluating field depends_on for', df.fieldname, ':', df.depends_on);
                    const condition_met = evaluate_depends_on(df.depends_on, ticket_doc);
                    debug_log('Result:', condition_met);
                    
                    if (!condition_met) {
                        debug_log('Skipping field', df.fieldname);
                        return;
                    }
                }

                // Ensure we have a container to append to
                if (!state.current_column) {
                    if (!state.current_section) {
                        state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
                        state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
                    }
                    if (!state.current_row) {
                        state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
                    }
                    state.current_column = $('<div class="form-column col-sm-6"></div>').appendTo(state.current_row);
                }

                const field_wrapper = $('<div class="frappe-control"></div>').appendTo(state.current_column);

                const field = frappe.ui.form.make_control({
                    df: df,
                    parent: field_wrapper,
                    only_input: false
                });

                field_controls[df.fieldname] = field;
                
                // Set up change handler using Frappe's built-in mechanism to mark form as dirty
                field.df.change = function() {
                    frm._sub_ticket_dirty = true;
                    frm.doc.__unsaved = 1;
                    frm.dirty();
                    frm.enable_save();
                };
                
                // If this is the ticket_type field, re-render form when it changes
                if (df.fieldname === 'ticket_type') {
                    const original_change = field.df.change;
                    const current_ticket_type = ticket_doc.ticket_type;
                    
                    field.df.change = function() {
                        const new_value = field.get_value();
                        
                        if (new_value && new_value !== current_ticket_type) {
                            // Save all current field values to ticket_doc before re-rendering
                            if (frm._sub_ticket_field_controls) {
                                save_field_values_to_doc(frm._sub_ticket_field_controls, ticket_doc);
                            }
                            
                            // Update ticket_type specifically
                            ticket_doc.ticket_type = new_value;
                            
                            if (original_change) original_change.call(this);
                            
                            // Re-render the form with new field visibility
                            setTimeout(function() { render_sub_ticket_form(frm); }, 150);
                        } else {
                            // Just call the original change handler without re-rendering
                            if (original_change) original_change.call(this);
                        }
                    };
                }
                
                // Set value AFTER change handler is configured to avoid triggering during initial set
                field.set_value(ticket_doc[df.fieldname]);
                field.refresh();
            });

            // Store controls for save handler
            frm._sub_ticket_field_controls = field_controls;
            frm._sub_ticket_dirty = false;
        });
    });
}

function save_sub_ticket(frm) {
    if (!frm._sub_ticket_dirty) {
        return;
    }

    const field_values = {};
    const controls = frm._sub_ticket_field_controls;

    for (let fieldname in controls) {
        field_values[fieldname] = controls[fieldname].get_value();
    }

    // Synchronous save to ensure it completes before the main form save
    return frappe.call({
        method: 'ivm.ivm_support.services.ticket_manager.save_sub_ticket',
        args: {
            ticket_doctype: frm.doc.sub_ticket_type,
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

function debug_log(...args) {
    if (frappe.boot.developer_mode) {
        console.log(...args);
    }
}

function evaluate_depends_on(depends_on, doc) {
    if (!depends_on) return true;
    
    try {
        let condition = depends_on.startsWith('eval:') 
            ? depends_on.substring(5) 
            : depends_on;
        return eval(condition);

    } catch(e) {
        debug_log('Error evaluating depends_on:', depends_on, e);
        return true; // Show field on error
    }
}

function save_field_values_to_doc(field_controls, ticket_doc) {
    for (let fieldname in field_controls) {
        try {
            const control = field_controls[fieldname];
            if (control?.get_value) {
                ticket_doc[fieldname] = control.get_value();
            }
        } catch(e) {
            debug_log('Error saving field', fieldname, e);
        }
    }
}

function handle_tab_break(df, ticket_doc, form_container, state) {
    // Treat Tab Breaks as major sections
    state.skip_current_section = false;

    // Check if tab is hidden
    if (df.hidden) {
        debug_log('Tab is hidden:', df.label || 'unlabeled');
        state.skip_current_section = true;
        return state;
    }

    // Check if this tab should be hidden via depends_on
    if (df.depends_on) {
        debug_log('Evaluating tab depends_on:', df.label || 'unlabeled', ':', df.depends_on);
        const condition_met = evaluate_depends_on(df.depends_on, ticket_doc);
        debug_log('Tab visible:', condition_met);
        
        if (!condition_met) {
            state.skip_current_section = true;
            return state;
        }
    }

    // Hide previous section if it has no actual field controls (only structural divs)
    if (state.current_section) {
        const has_fields = state.current_section.find('.frappe-control').length > 0;
        if (!has_fields) {
            state.current_section.hide();
        }
    }

    // Create section for the tab
    state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
    if (df.label) {
        state.current_section.append(`<div class="section-head">${df.label}</div>`);
    }
    state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
    state.current_column = $('<div class="form-column col-sm-6"></div>').appendTo(state.current_row);
    
    return state;
}

function handle_section_break(df, ticket_doc, form_container, state) {
    state.skip_current_section = false;

    // Check if section is hidden
    if (df.hidden) {
        debug_log('Section is hidden:', df.label || 'unlabeled');
        state.skip_current_section = true;
        return state;
    }

    // Check if this section should be hidden via depends_on
    if (df.depends_on) {
        debug_log('Evaluating section depends_on:', df.label || 'unlabeled', ':', df.depends_on);
        const condition_met = evaluate_depends_on(df.depends_on, ticket_doc);
        debug_log('Section visible:', condition_met);
        
        if (!condition_met) {
            state.skip_current_section = true;
            return state;
        }
    }

    // Create section
    state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
    if (df.label) {
        state.current_section.append(`<div class="section-head">${df.label}</div>`);
    }
    state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
    state.current_column = $('<div class="form-column col-sm-6"></div>').appendTo(state.current_row);
    
    return state;
}

function handle_column_break(state) {
    if (state.skip_current_section) return state;

    if (state.current_row) {
        state.current_column = $('<div class="form-column col-sm-6"></div>').appendTo(state.current_row);
    }
    return state;
}
