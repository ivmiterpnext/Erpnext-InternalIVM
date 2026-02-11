frappe.listview_settings["Customer"] = {
    hide_name_column: true,
    onload: function (me) {
      me.$page.find(`div[data-fieldname='name']`).addClass("hide");
    },
  };
  