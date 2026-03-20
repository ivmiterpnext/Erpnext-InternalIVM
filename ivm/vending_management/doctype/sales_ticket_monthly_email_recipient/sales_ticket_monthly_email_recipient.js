// Copyright (c) 2026, IVM and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Ticket Monthly Email Recipient", {
	contact(frm) {
		// When contact is selected, fetch and populate the email
		if (frm.doc.contact) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Contact",
					name: frm.doc.contact
				},
				callback: function(r) {
					if (r.message && r.message.email_ids && r.message.email_ids.length > 0) {
						// Find primary email or use first email
						let primary_email = null;
						let first_email = null;
						
						for (let email of r.message.email_ids) {
							if (!first_email) {
								first_email = email.name;
							}
							if (email.is_primary) {
								primary_email = email.name;
								break;
							}
						}
						
						// Set the contact_email field
						frm.set_value("contact_email", primary_email || first_email);
					}
				}
			});
		} else {
			// Clear contact_email if contact is cleared
			frm.set_value("contact_email", "");
		}
	}
});
