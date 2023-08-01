frappe.listview_settings["Opportunity"] = {
    hide_name_column: true,
    onload: function (me) {
      me.$page.find(`div[data-fieldname='name']`).addClass("hide");
    },
  };
  