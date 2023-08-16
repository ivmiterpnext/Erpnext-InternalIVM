frappe.ui.form.on("Issue", {
    issue_type: function(frm) {
        frappe.call({
            method: 'ivm.api.get_issue_type_record',
            args: {
                record_name: frm.doc.issue_type
            },
            callback: function(r) {
                const message = r.message;
                if (message) {
                    if (message.project_status) {
                        updateSelectFieldOptions(frm, 'status', message.project_status);
                    }
                    if (message.stage) {
                        updateSelectFieldOptions(frm, 'stage', message.stage);
                    }
                    if (message.case_origin) {
                        updateSelectFieldOptions(frm, 'case_origin', message.case_origin);
                    }
                    if (message.case_reason) {
                        filterLinkFieldOptions(frm, 'case_reason', message.case_reason);
                    }
                }
            }
        });
    }
});

function updateSelectFieldOptions(frm, fieldname, optionsData) {
    const optionsList = optionsData.map(option => option[fieldname]);
    frm.set_df_property(fieldname, 'options', optionsList);
    
    if (optionsList.length > 0) {
        frm.set_value(fieldname, optionsList[0]);
    }
    
    frm.refresh_field(fieldname);
}

function filterLinkFieldOptions(frm, fieldname, optionsData) {
    const optionsList = optionsData.map(option => option['case_reason']);
    const field = frm.fields_dict[fieldname];
    
    field.get_query = function(doc, cdt, cdn) {
        return {
            filters: [
                ['case_reason', 'in', optionsList]
            ]
        };
    };
    
    frm.refresh_field(fieldname);
}
