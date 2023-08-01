frappe.ui.form.on('User', {
    onload: function (frm) {

        frm.set_df_property('document_follow_notifications_section', 'hidden', 1);
        frm.set_df_property('api_access', 'hidden', 1);
        frm.set_df_property('location', 'hidden', 1)
        frm.set_df_property('mobile_no', 'hidden', 1)

        frm.refresh();
    }
});



