frappe.ui.form.on("Customer", {
	onload: function (frm) {
		$(document).ready(function () {
			$(".section-head").css({ color: "#2490EF", "font-size": "16px" });
		});
	},
	refresh: function (frm) {
		render_icorp_clients_html(frm);
	},
	validate: async function (frm) {
		if (frm.doc.__islocal) {
			const customerExists = await checkCustomerExists(frm.doc.customer_name);
			if (customerExists) {
				const confirmed = await showConfirmationPopup();
				if (!confirmed) {
					frappe.validated = false;
				}
			}
		}
		var sum =
			parseInt(frm.doc.number_of_lockers_in_place) +
			parseInt(frm.doc.number_of_machines_in_place);
		frm.set_value("custom_total_pieces_of_equipment_in_place", sum);
	},
});

function render_icorp_clients_html(frm) {
	const wrapper =
		frm.fields_dict.icorp_clients_html && frm.fields_dict.icorp_clients_html.$wrapper;
	if (!wrapper) {
		return;
	}
	const onload = frm.doc.__onload || {};
	const own = onload.icorp_clients || [];
	const managed = onload.icorp_managed_clients || [];

	const esc = frappe.utils.escape_html;
	const yesNo = (v) => (v ? __("Yes") : __("No"));

	let html = "";

	if (!own.length && !managed.length) {
		html += `<p class="text-muted">${__("No iCorp clients")}</p>`;
	}

	if (own.length) {
		html += `<h5>${__("iCorp clients assigned to this Customer")}</h5>`;
		const colgroup = `<colgroup>
			<col style="width: 25%;">
			<col style="width: 30%;">
			<col style="width: 25%;">
			<col style="width: 10%;">
			<col style="width: 10%;">
		</colgroup>`;
		const head = [__("iCorp Client"), __("Relationship"), __("Partner"), __("Active"), ""]
			.map((h) => `<th>${esc(h)}</th>`)
			.join("");
		const link_html = (doctype, name) =>
			name
				? `<a href="/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}">${esc(
						name
				  )}</a>`
				: "";
		const body = own
			.map(
				(r) => `<tr>
					<td>${esc(r.display_label || r.name)}</td>
					<td>${esc(r.relationship || "")}</td>
					<td>${link_html("Customer", r.partner_customer)}</td>
					<td>${yesNo(r.is_active)}</td>
					<td><button class="btn btn-xs btn-default remove-icorp-client-btn" data-client-id="${esc(
						r.name
					)}" data-client-label="${esc(r.display_label || r.name)}">${__(
					"Remove"
				)}</button></td>
				</tr>`
			)
			.join("");
		html += `<table class="table table-bordered table-condensed" style="table-layout: fixed;">${colgroup}<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
	}

	if (managed.length) {
		html += `<h5>${__("iCorp clients managed under this Customer's clients")}</h5>`;
		const head = [__("iCorp Client"), __("Customer"), __("Via"), __("Active")]
			.map((h) => `<th>${esc(h)}</th>`)
			.join("");
		const body = managed
			.map(
				(r) => `<tr>
					<td>${esc(r.display_label || r.name)}</td>
					<td>${esc(r.customer || __("Unassigned"))}</td>
					<td>${esc(r.via || "")}</td>
					<td>${yesNo(r.is_active)}</td>
				</tr>`
			)
			.join("");
		html += `<table class="table table-bordered table-condensed"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
	}

	const hubspot_companies = onload.hubspot_companies || [];
	html += `<h5>${__("HubSpot companies linked to this Customer")}</h5>`;
	if (!hubspot_companies.length) {
		html += `<p class="text-muted">${__("No HubSpot companies linked")}</p>`;
	} else {
		const items = hubspot_companies
			.map(
				(r) => `<li>
					<a href="/app/crm-organization/${encodeURIComponent(r.name)}">${esc(
					r.organization_name || r.name
				)}</a>
					${
						r.custom_hubspot_company_id
							? `<span class="text-muted">(HubSpot ${esc(
									r.custom_hubspot_company_id
							  )})</span>`
							: ""
					}
					<span class="text-muted">— ${esc(String(r.deal_count || 0))} ${__("deal(s)")}</span>
				</li>`
			)
			.join("");
		html += `<ul>${items}</ul>`;
	}

	html += `<div style="margin-top: 10px; margin-bottom: 15px;">
		<button class="btn btn-xs btn-default" id="add-icorp-client-btn">${__("Add iCorp client")}</button>
		<button class="btn btn-xs btn-default" id="create-icorp-client-btn">${__(
			"Create new in iCorp"
		)}</button>
	</div>`;

	wrapper.html(html);

	wrapper.find("#add-icorp-client-btn").on("click", () => open_add_icorp_client_dialog(frm));
	wrapper
		.find("#create-icorp-client-btn")
		.on("click", () => open_create_icorp_client_dialog(frm));
	wrapper.find(".remove-icorp-client-btn").on("click", function () {
		open_remove_icorp_client_dialog(
			frm,
			$(this).data("client-id"),
			$(this).data("client-label")
		);
	});
}

function open_add_icorp_client_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add iCorp client"),
		fields: [
			{
				fieldname: "client_id",
				label: __("iCorp Client ID"),
				fieldtype: "Data",
				reqd: 1,
			},
			{
				fieldname: "lookup_btn",
				fieldtype: "Button",
				label: __("Look up"),
				click: () => do_lookup(),
			},
			{
				fieldname: "result_html",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Add to Customer"),
		primary_action: () => {
			const client_id = dialog.get_value("client_id");
			frappe.call({
				method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.add_icorp_client_to_customer",
				args: { client_id, customer: frm.doc.name },
				freeze: true,
				callback: () => {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});

	dialog.disable_primary_action();

	function do_lookup() {
		const client_id = dialog.get_value("client_id");
		if (!client_id) {
			frappe.msgprint(__("Enter an iCorp Client ID first."));
			return;
		}
		frappe.call({
			method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.lookup_icorp_client",
			args: { client_id, customer: frm.doc.name },
			freeze: true,
			callback: (r) => {
				const d = r.message;
				if (!d) return;
				const esc = frappe.utils.escape_html;
				let summary = `<div class="small">
					<p><strong>${esc(d.client_id)} — ${esc(d.client_name)}</strong> (${
					d.is_active ? __("Active") : __("Inactive")
				})</p>
					<p>${__("Locations")}: ${d.sv_location_count_active}, ${__("Machines")}: ${
					d.sv_machine_count_active
				}</p>
					<p>${__("iCorp parent")}: ${
					d.parent_client_id
						? esc(d.parent_client_label || d.parent_client_id) +
						  (d.parent_customer ? ` (${esc(d.parent_customer)})` : "")
						: __("None")
				}</p>
				</div>`;

				let can_add = true;
				if (d.status === "already_on_this_customer") {
					summary += `<p class="text-muted">${__(
						"Already assigned to this Customer."
					)}</p>`;
					can_add = false;
				} else if (d.status === "assigned_elsewhere") {
					summary += `<p class="text-danger">${__(
						"This client is assigned to {0}. Remove it from {0} first.",
						[esc(d.current_customer)]
					)}</p>`;
					can_add = false;
				}

				dialog.fields_dict.result_html.$wrapper.html(summary);
				if (can_add) {
					dialog.enable_primary_action();
				} else {
					dialog.disable_primary_action();
				}
			},
		});
	}

	dialog.show();
}

function open_create_icorp_client_dialog(frm) {
	frappe.call({
		method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.get_customer_contacts",
		args: { customer: frm.doc.name },
		callback: (r) => {
			const contacts = r.message || [];
			if (!contacts.length) {
				frappe.msgprint({
					title: __("No Contact linked"),
					indicator: "orange",
					message: __(
						"This Customer has no Contacts yet. Add a Contact linked to {0} first, then try again.",
						[frm.doc.name]
					),
				});
				return;
			}
			show_create_icorp_client_dialog(frm, contacts);
		},
	});
}

function show_create_icorp_client_dialog(frm, contacts) {
	const contact_names = contacts.map((c) => c.name);
	const default_contact =
		frm.doc.customer_primary_contact &&
		contact_names.includes(frm.doc.customer_primary_contact)
			? frm.doc.customer_primary_contact
			: contact_names[0];

	const update_contact_warning = () => {
		const wrapper = dialog.fields_dict.contact_warning.$wrapper;
		const selected = contacts.find((c) => c.name === dialog.get_value("contact"));
		if (!selected) {
			wrapper.html("");
			dialog.disable_primary_action();
			return;
		}
		const esc = frappe.utils.escape_html;
		let html = "";
		if (!selected.phone) {
			html += `<div class="alert alert-danger small">${__(
				"iCorp requires at least one phone number on the contact. Add a phone number to {0} first.",
				[esc(selected.name)]
			)}</div>`;
		}
		if (!selected.email) {
			html += `<div class="alert alert-warning small">${__(
				"{0} has no email address. iCorp may reject a contact without an email address, so add one to the Contact first.",
				[esc(selected.display_name)]
			)}</div>`;
		}
		wrapper.html(html);
		if (selected.phone) {
			dialog.enable_primary_action();
		} else {
			dialog.disable_primary_action();
		}
	};

	const dialog = new frappe.ui.Dialog({
		title: __("Create new client in iCorp"),
		fields: [
			{
				fieldname: "warning_html",
				fieldtype: "HTML",
				options: `<div class="alert alert-warning">${__(
					"This creates a real client in iCorp. Frappe will also create a contact in iCorp from the Contact below."
				)}</div>`,
			},
			{
				fieldname: "client_name",
				label: __("Client Name"),
				fieldtype: "Data",
				reqd: 1,
				default: frm.doc.customer_name,
			},
			{
				fieldname: "contact",
				label: __("Primary Contact"),
				fieldtype: "Link",
				options: "Contact",
				reqd: 1,
				default: default_contact,
				get_query: () => ({ filters: { name: ["in", contact_names] } }),
				onchange: update_contact_warning,
			},
			{
				fieldname: "contact_warning",
				fieldtype: "HTML",
			},
			{
				fieldname: "partner_client",
				label: __("Managed by partner client"),
				fieldtype: "Link",
				options: "iCorp Client Link",
				description: __(
					"Optional. Leave blank unless a partner client manages this client in iCorp."
				),
				get_query: () => ({
					query: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.icorp_client_query",
				}),
			},
		],
		primary_action_label: __("Create in iCorp"),
		primary_action: (values) => {
			const selected = contacts.find((c) => c.name === values.contact);
			if (!selected || !selected.phone) {
				return;
			}
			frappe.confirm(
				__("Create {0} in iCorp now? This cannot be undone from Frappe.", [
					values.client_name,
				]),
				() => {
					frappe.call({
						method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.create_icorp_client_for_customer",
						args: {
							customer: frm.doc.name,
							client_name: values.client_name,
							contact: values.contact,
							partner_client_id: values.partner_client || null,
						},
						freeze: true,
						freeze_message: __("Creating client in iCorp..."),
						callback: (r) => {
							dialog.hide();
							frappe.show_alert({
								message: __("Created iCorp client {0}", [r.message.client_id]),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				}
			);
		},
	});

	dialog.show();
	// Disable submit until a phone is confirmed. A Link default does not fire onchange,
	// so evaluate the initial contact once here.
	update_contact_warning();
}

function open_remove_icorp_client_dialog(frm, client_id, client_label) {
	frappe.confirm(__("Remove {0} from {1}?", [client_label || client_id, frm.doc.name]), () => {
		frappe.call({
			method: "ivm.machine_hardware_management.doctype.icorp_client_link.icorp_client_link.remove_icorp_client_from_customer",
			args: { client_id, customer: frm.doc.name },
			freeze: true,
			callback: () => frm.reload_doc(),
		});
	});
}

async function checkCustomerExists(customerName) {
	return new Promise(function (resolve, reject) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Customer",
				filters: {
					customer_name: customerName,
				},
				fieldname: "name",
			},
			callback: function (customer_response) {
				resolve(!!customer_response.message.name);
			},
		});
	});
}

function showConfirmationPopup() {
	return new Promise(function (resolve, reject) {
		frappe.confirm(
			"A customer with the same name already exists. Do you want to continue?",
			function () {
				resolve(true);
			}
		);
	});
}
