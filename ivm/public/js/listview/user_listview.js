frappe.listview_settings["User"] = {
    hide_name_column: true,
    onload: function (me) {
        me.$page.find(`div[data-fieldname='username']`).addClass("hide");
        me.$page.find(`div[data-fieldname='user_type']`).addClass("hide");
        me.$page.find(`div[data-fieldname='id']`).addClass("hide");
        me.$page.find(`div[data-fieldname='name']`).addClass("hide");

    },
};