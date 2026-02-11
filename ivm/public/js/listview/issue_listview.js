frappe.listview_settings["Issue"] = {
    onload: function (me) {
        $('[data-fieldname="issue_type"]').attr("placeholder", "Case Record Type");
    },
};
