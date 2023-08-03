frappe.listview_settings["Lead"] = {
  hide_name_column: true,
  onload: function (me) {
    me.$page.find(`div[data-fieldname='name']`).addClass("hide");
    me.$page.find(`div[data-fieldname='title']`).addClass("hide");
  },
};
