frappe.ui.form.on("Service Quote", {
	refresh(frm) {
		frm.set_query("contact", "signers", function (doc) {
			if (doc.crm_deal) {
				return {
					query: "ivm.client_portal.services.queries.deal_contact_query",
					filters: { crm_deal: doc.crm_deal },
				};
			}
			if (doc.customer) {
				return {
					query: "frappe.contacts.doctype.contact.contact.contact_query",
					filters: { link_doctype: "Customer", link_name: doc.customer },
				};
			}
			return {};
		});
	},
	crm_deal(frm) {
		if (!frm.doc.crm_deal) return;
		frappe.call({
			method: "ivm.client_portal.services.quote_generation.get_deal_primary_contact",
			args: { crm_deal: frm.doc.crm_deal },
			callback: function (r) {
				if (r.message) {
					frm.set_value("contact", r.message);
				}
			},
		});
	},
});
