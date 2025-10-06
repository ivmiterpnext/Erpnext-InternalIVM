// Copyright (c) 2025, Dev and contributors
// For license information, please see license.txt

frappe.ui.form.on('Machine', {
    onload: function(frm) {
        frm.set_df_property('time_zone_id', 'hidden', 1);
        frm.set_df_property('allow_skip_job_code', 'read_only', 1);
        
        frm.set_query('agreement_fee_type_ids', function () {
            return {
                filters: {
                    'is_machine': 1
                }
            };
        });

        frm.set_query('location_id', function() {
            return {
                filters: {
                    client_id: frm.doc.client_id
                }
            };
        });
    },

    client_id: function(frm) {
        frm.set_query('location_id', function() {
            return {
                filters: {
                    client_id: frm.doc.client_id
                }
            };
        });
    },
    
    use_machine_timezone: function(frm) {
        onTimezoneCheckboxChange(frm);
    },
    
    use_job_code: function(frm) {
        onJobCodeCheckboxChange(frm);
    }
});

function onTimezoneCheckboxChange(frm) {
    if (frm.doc.use_machine_timezone) {
        frm.set_df_property('time_zone_id', 'hidden', 0);
    } else {
        frm.set_value('time_zone_id', 0);
        frm.set_df_property('time_zone_id', 'hidden', 1);

    }
}

function onJobCodeCheckboxChange(frm) {
    if (frm.doc.use_job_code) {
        frm.set_df_property('allow_skip_job_code', 'read_only', 0);
    } else {
        frm.set_value('allow_skip_job_code', 0);
        frm.set_df_property('allow_skip_job_code', 'read_only', 1);

    }
}