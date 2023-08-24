// Copyright (c) 2023, korecent and contributors
// For license information, please see license.txt

frappe.ui.form.on('SalesLoft Settings', {
	after_save: function(frm){
		if (frm.doc.enable_salesloft_integration===1){
			let email = frm.doc.salesloft_user_email
			let url = frm.doc.your_site_url
			let access_token = frm.doc.salesloft_api_token
			if (email =="" || email.length===0 || email===undefined || email===null){
				frappe.msgprint("Please enter email address and try again")
			}else if (url =="" || url.length===0 || url===undefined || url===null){
				frappe.msgprint("Please enter url and try again")
			}else if(access_token =="" || access_token.length===0 || access_token===undefined || access_token===null){
				frappe.msgprint("Please enter API Token and try again")
			}
			else{
				frappe.call({
					method: "ivm.salesloft_activity.create_webhooks",
					args:{}
				}).done((r)=>{
					console.log(r);
				})
			}
			
		}else{
			frappe.call({
				method: "ivm.salesloft_activity.delete_webhooks",
				args:{}
			}).done((r)=>{
				console.log(r);
			})
		}
	}
});
