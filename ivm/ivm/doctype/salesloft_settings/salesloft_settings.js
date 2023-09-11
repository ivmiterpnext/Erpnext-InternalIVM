// Copyright (c) 2023, korecent and contributors
// For license information, please see license.txt

frappe.ui.form.on('SalesLoft Settings', {
	after_save: function(frm){
		let email = frm.doc.salesloft_user_email
		let url = frm.doc.your_site_url
		let access_token = frm.doc.salesloft_api_token
		if (frm.doc.enable_salesloft_integration===1){
			
			if (email ==""){
				
			}else if (url ==""){
				
			}else if(access_token ==""){
				
			}
			else{
				frappe.call({
					method: "ivm.salesloft_activity.create_webhooks",
					args:{}
				}).done((r)=>{
					console.log(r);
				})
			}
			
		}else if(frm.doc.enable_salesloft_integration===0 && url !==""){
			frappe.call({
				method: "ivm.salesloft_activity.delete_webhooks",
				args:{}
			}).done((r)=>{
				console.log(r);
			})
		}
	}
});
