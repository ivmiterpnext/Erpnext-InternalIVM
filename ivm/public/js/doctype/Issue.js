frappe.ui.form.on("Issue", {
    refresh:function(frm){
        $(".badge-link:contains('Ticket')").closest(".document-link").find(".icon-btn").hide();
        $(".badge-link:contains('Warehouse Request')").closest(".document-link").find(".icon-btn").hide();
    },
    issue_type: function (frm) {
        if (frm.doc.issue_type) {
            frm.set_value("status", 'New');
            frm.refresh_field("status");
            frm.set_value("stage", '--None--');
            frm.refresh_field("stage");
            frm.set_value("case_origin", '--None--');
            frm.refresh_field("case_origin");
            frm.set_value("case_reason", '--None--');
            frm.refresh_field("case_reason");
            frappe.call({
                method: 'ivm.api.get_issue_type_record',
                args: {
                    record_name: frm.doc.issue_type
                },
                callback: function (r) {
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
    },
    connectivity_type: function (frm) {
        if (frm.doc.connectivity_type) {
            frappe.call({
                method: 'ivm.api.get_connectivity_type_record',
                args: {
                    record_name: frm.doc.connectivity_type
                },
                callback: function (r) {
                    const message = r.message;
                    if (message) {
                        if (message.cell_carrier) {
                            updateSelectFieldOptions(frm, 'cell_carrier', message.cell_carrier);
                        }
                    }
                }
            });
        }
    },
    case_reason: function (frm) {
        frappe.call({
            method: "ivm.api.get_case_sub_reason_options",
            args: { "case_reason": frm.doc.case_reason }
        }).done((r) => {
            let li = r.message
            set_field_options("case_sub_reason", li)
        });
    },
    customer: function (frm) {
        if (frm.doc.customer == "") {
            frm.set_value("contact_name", "")
        }

        frappe.call({
            method: "ivm.api.get_contact_name",
            args: { 'name': frm.doc.customer }
        }).done((r) => {
            let list_of_records = r.message
            cur_frm.set_query("contact_name", function () {
                return {
                    filters: {
                        "name": ['in', list_of_records]
                    }
                }
            });
        })
    },


    before_save: function (frm) {
        if (!frm.doc.case_number) {

            // Get the last case number from the database
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Issue',
                    fields: ['case_number'],
                    filters: [['case_number', '!=', '']],
                    order_by: 'case_number desc',
                    limit_page_length: 1
                },
                callback: function (response) {
                    if (response && response.message && response.message.length > 0) {
                        const lastCaseNumber = response.message[0].case_number;
                        const newCaseNumber = String(Number(lastCaseNumber) + 1).padStart(5, '0');
                        frm.doc.case_number = newCaseNumber;
                        frm.set_value('case_number', newCaseNumber);
                        frm.refresh_field('case_number');
                    }
                    else {
                        // If no previous case numbers exist, start with 00001
                        const newCaseNumber = '00001';
                        frm.set_value('case_number', newCaseNumber);
                        frm.refresh_field('case_number');
                    }

                }
            });
        }
    }



});

function updateSelectFieldOptions(frm, fieldname, optionsData) {
    const optionsList = optionsData.map(option => option[fieldname]);
    frm.set_df_property(fieldname, 'options', optionsList);
    frm.refresh_field(fieldname);
}

function filterLinkFieldOptions(frm, fieldname, optionsData) {
    const optionsList = optionsData.map(option => option['case_reason']);
    const field = frm.fields_dict[fieldname];

    field.get_query = function (doc, cdt, cdn) {
        return {
            filters: [
                ['case_reason', 'in', optionsList]
            ]
        };
    };

    frm.refresh_field(fieldname);
}

