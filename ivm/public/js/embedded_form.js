frappe.provide('ivm');

/**
 * EmbeddedForm - Renders a form for one DocType embedded within another
 * 
 * @example
 * frm.embedded_form = new ivm.EmbeddedForm({
 *     parent_form: frm,
 *     html_field_name: 'custom_sub_ticket_form',
 *     embedded_doctype_field: 'sub_ticket_type',
 *     dynamic_link_field: 'sub_ticket',
 *     save_method: 'ivm.ivm_support.services.ticket_manager.save_sub_ticket'
 * });
 * 
 * Note: To lock fields after first edit, set read_only_depends_on = "eval:!doc.__islocal && doc.modified != doc.creation;" on the field in the embedded DocType definition.
 */
ivm.EmbeddedForm = class {
    constructor(config) {
        // Required config
        this.parent_form = config.parent_form;
        this.html_field_name = config.html_field_name;
        this.embedded_doctype_field = config.embedded_doctype_field;
        this.dynamic_link_field = config.dynamic_link_field;
        this.save_method = config.save_method;
        
        // Optional config
        this.on_change_callback = config.on_change_callback;
        this.field_change_handler = config.field_change_handler;
        
        // Internal state
        this.field_controls = {};
        this.is_dirty = false;
        this.embedded_doc = null;
    }

    /**
     * Get the wrapper element for rendering
     */
    get_wrapper() {
        return this.parent_form.fields_dict[this.html_field_name].$wrapper;
    }

    /**
     * Get the linked doctype name
     */
    get_doctype() {
        return this.parent_form.doc[this.embedded_doctype_field];
    }

    /**
     * Get the linked document name
     */
    get_docname() {
        return this.parent_form.doc[this.dynamic_link_field];
    }

    /**
     * Check if form should be rendered
     */
    should_render() {
        return this.get_doctype() && this.get_docname();
    }

    /**
     * Clear the embedded form
     */
    clear() {
        const wrapper = this.get_wrapper();
        wrapper.empty();
        
        const parent_section = wrapper.closest('.form-section');
        if (parent_section.length) {
            parent_section.nextAll('.embedded-form').remove();
        }
        
        this.field_controls = {};
        this.is_dirty = false;
        this.embedded_doc = null;
    }

    /**
     * Render the embedded form
     */
    render() {
        const wrapper = this.get_wrapper();
        
        // Clear existing form
        this.clear();
        
        if (!this.should_render()) {
            return;
        }

        const doctype = this.get_doctype();
        const docname = this.get_docname();
        const self = this;

        // Load the document and metadata
        frappe.model.with_doc(doctype, docname, function() {
            self.embedded_doc = frappe.get_doc(doctype, docname);

            frappe.model.with_doctype(doctype, function() {
                const meta = frappe.get_meta(doctype);
                const form_container = $('<div class="embedded-form"></div>').appendTo(wrapper);

                // Move embedded form outside section-body for proper alignment
                const parent_body = wrapper.closest('.section-body');
                const parent_section = wrapper.closest('.form-section');
                if (parent_body.length && parent_section.length) {
                    form_container.detach();
                    parent_section.after(form_container);
                    parent_section.hide();
                    parent_section.addClass('embedded-form-parent');
                }

                // Render fields
                self._render_fields(meta, form_container);
            });
        });
    }

    /**
     * Render all fields from metadata
     * @private
     */
    _render_fields(meta, form_container) {
        const state = {
            current_section: null,
            current_row: null,
            current_column: null,
            skip_current_section: false
        };

        const self = this;

        meta.fields.forEach(function(df) {
            if (df.fieldtype === 'Tab Break') {
                self._handle_tab_break(df, form_container, state);
                return;
            }

            if (df.fieldtype === 'Section Break') {
                self._handle_section_break(df, form_container, state);
                return;
            }

            if (df.hidden) return;

            if (df.fieldtype === 'Column Break') {
                self._handle_column_break(state);
                return;
            }
            
            // Skip all fields if in a hidden section
            if (state.skip_current_section) {
                ivm.utils.debug_log('Skipping field', df.fieldname, '(in hidden section)');
                return;
            }
            
            // Evaluate field's depends_on
            if (df.depends_on) {
                ivm.utils.debug_log('Evaluating field depends_on for', df.fieldname, ':', df.depends_on);
                const condition_met = self._evaluate_depends_on(df.depends_on);
                if (!condition_met) {
                    ivm.utils.debug_log('Skipping field', df.fieldname);
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

            self._render_field(df, state.current_column);
        });

        // Mark as not dirty after initial render
        this.is_dirty = false;
    }

    /**
     * Render a single field
     * @private
     */
    _render_field(df, container) {
        const field_wrapper = $('<div class="frappe-control"></div>').appendTo(container);
        const self = this;

        const field = frappe.ui.form.make_control({
            df: df,
            parent: field_wrapper,
            only_input: false
        });

        this.field_controls[df.fieldname] = field;
        
        // Evaluate read_only_depends_on if defined
        if (df.read_only_depends_on) {
            const should_be_readonly = this._evaluate_depends_on(df.read_only_depends_on);
            if (should_be_readonly) {
                field.df.read_only = 1;
            }
        }
        
        // Set up change handler
        field.df.change = function() {
            self.is_dirty = true;
            self.parent_form.doc.__unsaved = 1;
            self.parent_form.dirty();
            self.parent_form.enable_save();
            
            if (self.on_change_callback) {
                self.on_change_callback(df.fieldname);
            }
        };
        
        // Special handling for ticket_type field - re-render on change to update depends_on visibility
        if (df.fieldname === 'ticket_type') {
            const original_change = field.df.change;
            
            field.df.change = function() {
                const new_value = field.get_value();
                const current_value = self.embedded_doc.ticket_type;
                
                if (new_value && new_value !== current_value) {
                    // Save all current field values to embedded_doc before re-rendering
                    self._save_field_values();
                    
                    // Update ticket_type specifically
                    self.embedded_doc.ticket_type = new_value;
                    
                    if (original_change) original_change.call(this);
                    
                    // Re-render the form with new field visibility
                    setTimeout(function() { self.render(); }, 150);
                } else {
                    // Just call the original change handler without re-rendering
                    if (original_change) original_change.call(this);
                }
            };
        }
        
        // Custom field change handlers (if provided)
        if (self.field_change_handler && self.field_change_handler[df.fieldname]) {
            const original_change = field.df.change;
            const handler = self.field_change_handler[df.fieldname];
            
            field.df.change = function() {
                if (original_change) original_change.call(this);
                handler.call(self, field.get_value());
            };
        }
        
        // Set value AFTER change handler is configured
        field.set_value(this.embedded_doc[df.fieldname]);
        field.refresh();
    }

    /**
     * Handle Tab Break fields
     * @private
     */
    _handle_tab_break(df, form_container, state) {
        state.skip_current_section = false;

        // Check if tab is hidden
        if (df.hidden) {
            ivm.utils.debug_log('Tab is hidden:', df.label || 'unlabeled');
            state.skip_current_section = true;
            return;
        }

        // Check depends_on
        if (df.depends_on) {
            ivm.utils.debug_log('Evaluating tab depends_on:', df.label || 'unlabeled', ':', df.depends_on);
            const condition_met = this._evaluate_depends_on(df.depends_on);
            ivm.utils.debug_log('Tab visible:', condition_met);
            
            if (!condition_met) {
                state.skip_current_section = true;
                return;
            }
        }

        // Hide previous empty section
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
    }

    /**
     * Handle Section Break fields
     * @private
     */
    _handle_section_break(df, form_container, state) {
        state.skip_current_section = false;

        // Check if section is hidden
        if (df.hidden) {
            ivm.utils.debug_log('Section is hidden:', df.label || 'unlabeled');
            state.skip_current_section = true;
            return;
        }

        // Check depends_on
        if (df.depends_on) {
            ivm.utils.debug_log('Evaluating section depends_on:', df.label || 'unlabeled', ':', df.depends_on);
            const condition_met = this._evaluate_depends_on(df.depends_on);
            ivm.utils.debug_log('Section visible:', condition_met);
            
            if (!condition_met) {
                state.skip_current_section = true;
                return;
            }
        }

        // Create section
        state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
        if (df.label) {
            state.current_section.append(`<div class="section-head">${df.label}</div>`);
        }
        state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
        state.current_column = $('<div class="form-column col-sm-6"></div>').appendTo(state.current_row);
    }

    /**
     * Handle Column Break fields
     * @private
     */
    _handle_column_break(state) {
        if (state.skip_current_section) return;

        if (state.current_row) {
            state.current_column = $('<div class="form-column col-sm-6"></div>').appendTo(state.current_row);
        }
    }

    /**
     * Evaluate depends_on condition against the embedded document
     * @private
     */
    _evaluate_depends_on(depends_on) {
        if (!depends_on) return true;
        
        try {
            // Make doc available in eval context for conditions like "eval:doc.ticket_type=='Support'"
            const doc = this.embedded_doc;
            
            let condition = depends_on.startsWith('eval:') 
                ? depends_on.substring(5) 
                : depends_on;
            return eval(condition);
        } catch(e) {
            ivm.utils.debug_warn('Error evaluating depends_on:', depends_on, e);
            return true; // Show field on error
        }
    }

    /**
     * Save field values from controls to embedded document
     * @private
     */
    _save_field_values() {
        for (let fieldname in this.field_controls) {
            try {
                const control = this.field_controls[fieldname];
                if (control?.get_value) {
                    this.embedded_doc[fieldname] = control.get_value();
                }
            } catch(e) {
                ivm.utils.debug_log('Error saving field', fieldname, e);
            }
        }
    }

    /**
     * Save the embedded form
     * @returns {Promise} Frappe call promise
     */
    save() {
        if (!this.is_dirty) {
            return Promise.resolve();
        }

        const field_values = {};
        for (let fieldname in this.field_controls) {
            field_values[fieldname] = this.field_controls[fieldname].get_value();
        }

        const self = this;

        // Return Promise so before_save hook can await completion
        return frappe.call({
            method: this.save_method,
            args: {
                ticket_doctype: this.get_doctype(),
                ticket_name: this.get_docname(),
                field_values: field_values
            },
            callback: function(r) {
                if (!r.exc) {
                    self.is_dirty = false;
                    
                    // Update embedded_doc with saved values to prevent fields from clearing
                    for (let fieldname in field_values) {
                        if (self.embedded_doc) {
                            self.embedded_doc[fieldname] = field_values[fieldname];
                        }
                    }
                    
                    // Also update the frappe model cache
                    const doctype = self.get_doctype();
                    const docname = self.get_docname();
                    const cached_doc = frappe.get_doc(doctype, docname);
                    if (cached_doc) {
                        for (let fieldname in field_values) {
                            cached_doc[fieldname] = field_values[fieldname];
                        }
                    }
                }
            }
        });
    }
};
