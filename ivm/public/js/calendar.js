frappe.listview_settings['Calendar Events'] = {
    refresh: function(listview) {
        frappe.call({
            method: "ivm.access_token.get_events",
            args : {}
        }).done((r)=>{
            console.log(r);
        })
    }
};