frappe.provide('ivm');

/**
 * EmbeddedForm - Renders a form for one DocType embedded within another.
 *
 * Supports two modes:
 *   - Editable (default): tracks dirty state, saves via a whitelisted method.
 *   - Read-only: renders all fields as read-only, no dirty tracking or saving.
 *
 * @example — Editable
 * frm.embedded_form = new ivm.EmbeddedForm({
 *     parent_form: frm,
 *     html_field_name: 'my_html_field',
 *     embedded_doctype_field: 'linked_doctype',
 *     dynamic_link_field: 'linked_docname',
 *     save_method: 'myapp.api.save_embedded_doc',
 * });
 *
 * @example — Read-only
 * frm.embedded_form = new ivm.EmbeddedForm({
 *     parent_form: frm,
 *     html_field_name: 'my_html_field',
 *     embedded_doctype_field: 'source_detail_doctype',
 *     dynamic_link_field: 'source_detail_row',
 *     readOnly: true,
 * });
 *
 * Note: To lock fields after first edit, set read_only_depends_on on the field
 * in the embedded DocType definition.
 */
ivm.EmbeddedForm = class {
    constructor(config) {
        // Required config
        this.parent_form = config.parent_form;
        this.html_field_name = config.html_field_name;
        this.embedded_doctype_field = config.embedded_doctype_field;
        this.dynamic_link_field = config.dynamic_link_field;

        // Mode
        this.readOnly = config.readOnly || false;
        this.hideEmptyFields = config.hideEmptyFields || false;

        // Optional extra gating condition, evaluated in addition to
        // "doctype + docname both resolved". Lets host doctypes add
        // supplementary rules (e.g. schema_version checks) without needing
        // to gate the render()/clear() call themselves.
        this.extra_condition = config.extra_condition || (() => true);

        // Editable-only config
        this.save_method = config.save_method || null;
        this.on_change_callback = config.on_change_callback || null;
        this.field_change_handler = config.field_change_handler || null;

        // Fieldnames that trigger a full re-render when changed (editable mode only).
        this.rerender_on_change = config.rerender_on_change || [];

        // Custom renderers: map of fieldname → function($container, value, df)
        // When provided, the function is called instead of the default make_control
        // path, allowing completely custom HTML for specific fields.
        this.custom_renderers = config.custom_renderers || {};

        // Internal state
        this.field_controls = {};
        this.is_dirty = false;
        this.embedded_doc = null;

        this._register_auto_sync();
        this.render();
    }

    /**
     * Get the wrapper element for rendering.
     */
    get_wrapper() {
        return this.parent_form.fields_dict[this.html_field_name].$wrapper;
    }

    /**
     * Get the linked doctype name.
     */
    get_doctype() {
        return this.parent_form.doc[this.embedded_doctype_field];
    }

    /**
     * Get the linked document name.
     */
    get_docname() {
        return this.parent_form.doc[this.dynamic_link_field];
    }

    /**
     * Check if form should be rendered.
     */
    should_render() {
        return this.get_doctype() && this.get_docname() && this.extra_condition();
    }

    /**
     * Ensure render() is invoked on every refresh of the parent form,
     * regardless of whether/how the host doctype's own refresh handler
     * calls it. This prevents stale embedded content from a previously
     * rendered document lingering when the current document no longer
     * qualifies (different request_reason, missing source fields, etc.)
     * but the host's own gating logic skips calling render()/clear().
     * @private
     */
    _register_auto_sync() {
        const frm = this.parent_form;

        if (!frm.__embedded_forms) {
            frm.__embedded_forms = [];
            const original_refresh = frm.refresh.bind(frm);
            frm.refresh = function(...args) {
                const result = original_refresh(...args);
                frm.__embedded_forms.forEach(function(ef) { ef.render(); });
                return result;
            };
        }

        frm.__embedded_forms.push(this);
    }

    /**
     * Clear the embedded form.
     */
    clear() {
        const wrapper = this.get_wrapper();
        wrapper.empty();

        // Remove any previously injected embedded form containers
        // and restore the parent section if we hid it.
        const parent_section = wrapper.closest('.form-section');
        if (parent_section.length) {
            parent_section.nextAll('.embedded-form').remove();
            if (parent_section.hasClass('embedded-form-parent-section')) {
                parent_section.show().removeClass('embedded-form-parent-section');
            }
        }

        this.field_controls = {};
        this.is_dirty = false;
        this.embedded_doc = null;
    }

    /**
     * Render the embedded form.
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

        // Ensure meta is loaded first, then decide how to fetch the doc.
        // Child table rows (istable=1) are not served by the standard
        // frappe.model.with_doc client API — fetch via dedicated endpoint.
        frappe.model.with_doctype(doctype, function() {
            const meta = frappe.get_meta(doctype);

            const _do_render = function(doc) {
                self.embedded_doc = doc;

                const form_container = $('<div class="embedded-form"></div>');

                // Insert the embedded form after the parent section so it
                // renders as a sibling of the parent form's sections.
                const parent_section = wrapper.closest('.form-section');
                if (parent_section.length) {
                    parent_section.after(form_container);
                    parent_section.hide().addClass('embedded-form-parent-section');
                } else {
                    wrapper.append(form_container);
                }

                self._render_fields(meta, form_container);
            };

            if (meta.istable) {
                frappe.call({
                    method: 'ivm.utils.get_child_table_row',
                    args: { doctype, name: docname },
                    callback: function(r) {
                        if (r.message) _do_render(r.message);
                    }
                });
            } else {
                frappe.model.with_doc(doctype, docname, function() {
                    _do_render(frappe.get_doc(doctype, docname));
                });
            }
        });
    }

    /**
     * Pre-compute column counts per section so we can pick the right Bootstrap
     * column width class (col-sm-6 for 2 cols, col-sm-4 for 3, col-sm-3 for 4).
     * @private
     */
    _compute_section_col_classes(meta) {
        const section_col_class = {};
        let current_section = '__default__';
        let col_breaks = 0;

        meta.fields.forEach(function(df) {
            if (df.fieldtype === 'Section Break' || df.fieldtype === 'Tab Break') {
                // Store result for previous section
                const cols = col_breaks + 1;
                const cls = cols <= 1 ? 'col-sm-12'
                          : cols === 2 ? 'col-sm-6'
                          : cols === 3 ? 'col-sm-4'
                          : 'col-sm-3';
                section_col_class[current_section] = cls;
                current_section = df.fieldname || df.fieldtype;
                col_breaks = 0;
            } else if (df.fieldtype === 'Column Break') {
                col_breaks++;
            }
        });
        // Last section
        const cols = col_breaks + 1;
        section_col_class[current_section] = cols <= 1 ? 'col-sm-12'
            : cols === 2 ? 'col-sm-6'
            : cols === 3 ? 'col-sm-4'
            : 'col-sm-3';

        return section_col_class;
    }

    /**
     * Render all fields from metadata.
     * @private
     */
    _render_fields(meta, form_container) {
        const section_col_class = this._compute_section_col_classes(meta);

        const state = {
            current_section: null,
            current_row: null,
            current_column: null,
            skip_current_section: false,
            col_class: section_col_class['__default__'] || 'col-sm-6',
            section_col_class: section_col_class,
            // Pending layout info (read-only mode: defer DOM creation until a
            // field actually needs to be rendered).
            pending_section_label: null,
            pending_column_break: false,
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
            if (state.skip_current_section) return;

            // Evaluate field's depends_on
            if (df.depends_on) {
                const condition_met = self._evaluate_depends_on(df.depends_on);
                if (!condition_met) return;
            }

            // In read-only mode, optionally skip fields with no value
            if (self.readOnly && self.hideEmptyFields) {
                const val = self.embedded_doc[df.fieldname];
                if (val === null || val === undefined || val === '') return;
            }

            // Materialise any pending section/column DOM now that we have a
            // field to render.
            if (state.pending_section_label !== null) {
                state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
                if (state.pending_section_label) {
                    state.current_section.append(`<div class="section-head">${state.pending_section_label}</div>`);
                }
                state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
                state.current_column = $(`<div class="form-column ${state.col_class}"></div>`).appendTo(state.current_row);
                state.pending_section_label = null;
                state.pending_column_break = false;
            } else if (state.pending_column_break) {
                if (state.current_row) {
                    state.current_column = $(`<div class="form-column ${state.col_class}"></div>`).appendTo(state.current_row);
                }
                state.pending_column_break = false;
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
                state.current_column = $(`<div class="form-column ${state.col_class}"></div>`).appendTo(state.current_row);
            }

            self._render_field(df, state.current_column);
        });

        // Remove empty columns, then empty section-body rows, then empty sections.
        form_container.find('.form-column').each(function() {
            if ($(this).find('.frappe-control').length === 0) {
                $(this).remove();
            }
        });
        form_container.find('.section-body').each(function() {
            if ($(this).children().length === 0) {
                $(this).remove();
            }
        });
        form_container.find('.form-section').each(function() {
            if ($(this).find('.frappe-control').length === 0) {
                $(this).remove();
            }
        });

        // Mark as not dirty after initial render
        this.is_dirty = false;
    }

    /**
     * Render a single field.
     * @private
     */
    _render_field(df, container) {
        const self = this;

        // Use a custom renderer if one is registered for this field
        if (this.custom_renderers[df.fieldname]) {
            const field_wrapper = $('<div class="frappe-control"></div>').appendTo(container);
            this.custom_renderers[df.fieldname](
                field_wrapper,
                this.embedded_doc[df.fieldname],
                df,
            );
            return;
        }

        // In read-only mode, render Attach/Attach Image as a labelled hyperlink.
        // Skip entirely if there is no value.
        if (this.readOnly && (df.fieldtype === 'Attach' || df.fieldtype === 'Attach Image')) {
            const value = this.embedded_doc[df.fieldname];
            if (!value) return;
            const field_wrapper = $('<div class="frappe-control"></div>').appendTo(container);
            field_wrapper.append(`
                <div class="form-group">
                    <label class="control-label">${df.label || df.fieldname}</label>
                    <div class="control-value">
                        <a href="${frappe.utils.escape_html(value)}" target="_blank" rel="noopener noreferrer">
                            ${frappe.utils.escape_html(value.split('/').pop())}
                        </a>
                    </div>
                </div>
            `);
            return;
        }

        const field_wrapper = $('<div class="frappe-control"></div>').appendTo(container);

        // In read-only mode force all fields read-only
        const field_df = this.readOnly
            ? Object.assign({}, df, { read_only: 1 })
            : Object.assign({}, df);

        const field = frappe.ui.form.make_control({
            df: field_df,
            parent: field_wrapper,
            only_input: false
        });

        this.field_controls[df.fieldname] = field;

        if (!this.readOnly) {
            // Evaluate read_only_depends_on if defined
            if (df.read_only_depends_on) {
                const should_be_readonly = this._evaluate_depends_on(df.read_only_depends_on);
                if (should_be_readonly) {
                    field.df.read_only = 1;
                }
            }

            // Base change handler — dirty tracking
            field.df.change = function() {
                self.is_dirty = true;
                self.parent_form.doc.__unsaved = 1;
                self.parent_form.dirty();
                self.parent_form.enable_save();

                if (self.on_change_callback) {
                    self.on_change_callback(df.fieldname);
                }
            };

            // Fields that trigger a full re-render on change
            if (self.rerender_on_change.includes(df.fieldname)) {
                const original_change = field.df.change;

                field.df.change = function() {
                    const new_value = field.get_value();
                    const current_value = self.embedded_doc[df.fieldname];

                    if (new_value && new_value !== current_value) {
                        self._save_field_values();
                        self.embedded_doc[df.fieldname] = new_value;
                        if (original_change) original_change.call(this);
                        setTimeout(function() { self.render(); }, 150);
                    } else {
                        if (original_change) original_change.call(this);
                    }
                };
            }

            // Custom per-field change handlers
            if (self.field_change_handler && self.field_change_handler[df.fieldname]) {
                const original_change = field.df.change;
                const handler = self.field_change_handler[df.fieldname];

                field.df.change = function() {
                    if (original_change) original_change.call(this);
                    handler.call(self, field.get_value());
                };
            }
        }

        // Set value AFTER change handler is configured
        field.set_value(this.embedded_doc[df.fieldname]);
        field.refresh();
    }

    /**
     * Handle Tab Break fields.
     * @private
     */
    _handle_tab_break(df, form_container, state) {
        state.skip_current_section = false;

        // Check if tab is hidden
        if (df.hidden) {
            state.skip_current_section = true;
            return;
        }

        // Check depends_on
        if (df.depends_on) {
            const condition_met = this._evaluate_depends_on(df.depends_on);

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

        // Update col_class for this tab's section
        state.col_class = state.section_col_class[df.fieldname] || 'col-sm-6';

        // Create section for the tab
        state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
        if (df.label) {
            state.current_section.append(`<div class="section-head">${df.label}</div>`);
        }
        state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
        state.current_column = $(`<div class="form-column ${state.col_class}"></div>`).appendTo(state.current_row);
    }

    /**
     * Handle Section Break fields.
     * @private
     */
    _handle_section_break(df, form_container, state) {
        state.skip_current_section = false;
        state.pending_section_label = null;
        state.pending_column_break = false;

        // Check if section is hidden
        if (df.hidden) {
            state.skip_current_section = true;
            return;
        }

        // Check depends_on
        if (df.depends_on) {
            const condition_met = this._evaluate_depends_on(df.depends_on);

            if (!condition_met) {
                state.skip_current_section = true;
                return;
            }
        }

        // Update col_class for this section
        state.col_class = state.section_col_class[df.fieldname] || 'col-sm-6';

        if (this.readOnly) {
            // Defer DOM creation until a field actually needs to be rendered.
            state.pending_section_label = df.label || '';
            state.current_section = null;
            state.current_row = null;
            state.current_column = null;
        } else {
            // Create section immediately in editable mode.
            state.current_section = $('<div class="form-section"></div>').appendTo(form_container);
            if (df.label) {
                state.current_section.append(`<div class="section-head">${df.label}</div>`);
            }
            state.current_row = $('<div class="section-body"></div>').appendTo(state.current_section);
            state.current_column = $(`<div class="form-column ${state.col_class}"></div>`).appendTo(state.current_row);
        }
    }

    /**
     * Handle Column Break fields.
     * @private
     */
    _handle_column_break(state) {
        if (state.skip_current_section) return;

        if (this.readOnly) {
            // Defer column break until a field needs to be rendered.
            state.pending_column_break = true;
            state.current_column = null;
        } else {
            if (state.current_row) {
                state.current_column = $(`<div class="form-column ${state.col_class}"></div>`).appendTo(state.current_row);
            }
        }
    }

    /**
     * Evaluate depends_on condition against the embedded document.
     * @private
     */
    _evaluate_depends_on(depends_on) {
        if (!depends_on) return true;

        try {
            // Make doc available in eval context for conditions like "eval:doc.field=='value'"
            const doc = this.embedded_doc;

            let condition = depends_on.startsWith('eval:')
                ? depends_on.substring(5)
                : depends_on;
            return eval(condition);
        } catch(e) {
            console.warn('Error evaluating depends_on:', depends_on, e);
            return true; // Show field on error
        }
    }

    /**
     * Save field values from controls to embedded document.
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
            }
        }
    }

    /**
     * Save the embedded form.
     * No-op in read-only mode.
     * @returns {Promise}
     */
    save() {
        if (this.readOnly || !this.is_dirty) {
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
                doctype: this.get_doctype(),
                docname: this.get_docname(),
                field_values: field_values
            },
            callback: function(r) {
                if (!r.exc) {
                    self.is_dirty = false;

                    // Update embedded_doc with saved values
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
